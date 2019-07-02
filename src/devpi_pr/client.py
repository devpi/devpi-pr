from contextlib import contextmanager
from devpi_common.metadata import parse_requirement
from operator import itemgetter
from pluggy import HookimplMarker
from tempfile import NamedTemporaryFile
from subprocess import call
import appdirs
import attr
import json
import os
import textwrap
import traceback


client_hookimpl = HookimplMarker("devpiclient")
devpi_pr_data_dir = appdirs.user_data_dir("devpi-pr", "devpi")


def get_message_from_file(f):
    lines = f.read().decode('utf-8').splitlines()
    msg = '\n'.join(x for x in lines if not x.strip().startswith('#'))
    return msg.strip()


def get_message(hub, msg):
    if msg and msg.strip():
        return msg
    editor = os.environ.get("EDITOR")
    if not editor:
        hub.fatal("No EDITOR environment variable set.")
    with NamedTemporaryFile(prefix="devpi-pr-", suffix=".txt") as tf:
        tf.write(textwrap.dedent("""\n
            # Please enter the message for your push request.
            # Lines starting with '#' will be ignored.
            # An empty message aborts the current command.""").encode('utf-8'))
        tf.flush()
        try:
            result = call([editor, tf.name])
        except Exception as e:
            hub.fatal(''.join(traceback.format_exception(e.__class__, e, None)))
        if result != 0:
            hub.fatal("Error (%s) calling editor %s" % (result, editor))
        tf.seek(0)
        msg = get_message_from_file(tf)
        if not msg:
            # try to reopen the file. vim seems to replace it.
            with open(tf.name, 'rb') as f:
                msg = get_message_from_file(f)
        if msg:
            return msg
    hub.fatal("A message is required.")


@contextmanager
def devpi_pr_review_lock(hub):
    if not os.path.exists(devpi_pr_data_dir):
        os.mkdir(devpi_pr_data_dir)
    lock_fn = os.path.join(devpi_pr_data_dir, "reviews.lock")
    try:
        with open(lock_fn, "x"):
            yield
    except FileExistsError:
        hub.fatal(
            "There is an existing lock at %s\n"
            "This can happen if a previous devpi-pr command crashed. "
            "If you are sure there is no other devpi-pr command still running, "
            "you can remove the file." % lock_fn)
    else:
        if os.path.exists(lock_fn):
            os.remove(lock_fn)


@contextmanager
def devpi_pr_review_data(hub):
    with devpi_pr_review_lock(hub):
        fn = os.path.join(devpi_pr_data_dir, "reviews.json")
        if os.path.exists(fn):
            with open(fn, "rb") as f:
                data = f.read().decode("utf-8")
        else:
            data = ""
        if not data:
            original = None
            info = {}
        else:
            original = json.loads(data)
            info = dict(original)
        yield info
        if info != original:
            with open(fn, "wb") as f:
                f.write(json.dumps(info).encode("utf-8"))


def full_indexname(hub, prname):
    if '/' in prname:
        try:
            user, prname = prname.split('/')
        except ValueError:
            hub.fatal("Invalid index name")
    else:
        user = hub.current.get_auth_user()
    return "%s/%s" % (user, prname)


@attr.s
class MergeIndexInfos:
    user = attr.ib(type=str)
    index = attr.ib(type=str)
    indexname = attr.ib(type=str)
    url = attr.ib(type=str)
    ixconfig = attr.ib(type=dict)


def require_merge_index(hub, name):
    hub.requires_login()
    current = hub.require_valid_current_with_index()
    indexname = full_indexname(hub, name)
    (user, index) = indexname.split('/')
    url = current.get_index_url(indexname, slash=False)
    result = hub.http_api("get", url, fatal=False)
    if result.reason != 'OK':
        hub.fatal("Couldn't access merge index '%s': %s" % (
            name, result.reason))
    ixconfig = result.result
    if ixconfig['type'] != 'merge':
        hub.fatal("The index '%s' is not a merge index" % name)
    return MergeIndexInfos(user, index, indexname, url, ixconfig)


def new_pr_arguments(parser):
    """ create push request
    """
    parser.add_argument(
        "name", metavar="NAME", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "target", metavar="TARGETSPEC", type=str, nargs=1,
        action="store",
        help="target index of form 'USER/NAME'")
    parser.add_argument(
        "pkgspec", metavar="PKGSPEC", type=str, nargs="*",
        default=None, action="store",
        help="releases in format 'name==version' which are added to "
             "this push request.")


def new_pr(hub, args):
    (name,) = args.name
    (target,) = args.target
    reqs = []
    for pkgspec in args.pkgspec:
        req = parse_requirement(pkgspec)
        if len(req.specs) != 1 or req.specs[0][0] != '==':
            hub.fatal(
                "The release specification needs to be of this form: name==version")
        reqs.append(req)
    indexname = full_indexname(hub, name)
    url = hub.current.get_index_url(indexname, slash=False)
    hub.http_api("put", url, dict(
        type="merge", bases=target,
        states=["new"], messages=["New push request"]))
    for req in reqs:
        hub.http_api(
            "push",
            hub.current.index,
            kvdict=dict(
                name=req.project_name,
                version="%s" % req.specs[0][1],
                targetindex=indexname),
            fatal=True)


def abort_pr_review_arguments(parser):
    """ abort review of push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")


def abort_pr_review(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    with devpi_pr_review_data(hub) as review_data:
        if indexinfos.indexname in review_data:
            hub.info("Aborted review of '%s'" % indexinfos.indexname)
            del review_data[indexinfos.indexname]
        else:
            hub.error("No review of '%s' active" % indexinfos.indexname)


def approve_pr_arguments(parser):
    """ approve push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "-s", "--serial", type=str, action="store",
        help="push request serial, only required if not using 'review-pr' first")
    parser.add_argument(
        "-m", "--message", action="store",
        help="Message to add on submit.")
    parser.add_argument(
        "-k", "--keep-index", action="store_true",
        help="Keep the merge index instead of deleting it after approval.")


def approve_pr(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    serial = args.serial
    if serial is None:
        with devpi_pr_review_data(hub) as review_data:
            if indexinfos.indexname not in review_data:
                hub.fatal(
                    "No review data found for '%s', "
                    "it looks like you did not use review-pr or "
                    "you forgot the --serial option." % indexinfos.indexname)
            serial = "%s" % review_data[indexinfos.indexname]
    message = get_message(hub, args.message)
    hub.http_api(
        "patch", indexinfos.url, [
            "states+=approved",
            "messages+=%s" % message],
        headers={'X-Devpi-PR-Serial': serial})
    if not args.keep_index:
        hub.http_api("delete", indexinfos.url)
    with devpi_pr_review_data(hub) as review_data:
        review_data.pop(indexinfos.indexname, None)


def list_prs_arguments(parser):
    """ list push requests
    """
    parser.add_argument(
        "indexname", type=str, action="store", nargs="?",
        help="index name, specified as NAME or USER/NAME.  If no index "
             "is specified use the current index")
    parser.add_argument(
        "-a", "--all-states", action="store_true",
        help="Output normally hidden states.")
    parser.add_argument(
        "-m", "--messages", action="store_true",
        help="Include state change messages in output.")


def merge_pr_data(data1, data2):
    states = set(data1).union(data2)
    result = {}
    for state in states:
        state_data = result[state] = {}
        state_data1 = data1.get(state, {})
        state_data2 = data2.get(state, {})
        users = set(state_data1).union(state_data2)
        for user in users:
            user_data1 = set(
                tuple(
                    (k, tuple(v) if isinstance(v, list) else v)
                    for k, v in x.items())
                for x in state_data1.get(user, []))
            user_data2 = set(
                tuple(
                    (k, tuple(v) if isinstance(v, list) else v)
                    for k, v in x.items())
                for x in state_data2.get(user, []))
            state_data[user] = list(
                dict(x)
                for x in user_data1.union(user_data2))
    return result


def get_prs(users_prs):
    result = []
    for user, prs in users_prs.items():
        for pr in prs:
            result.append(dict(pr, name="%s/%s" % (user, pr['name'])))
    return sorted(result, key=itemgetter("name", "base", "last_serial"))


def create_pr_list_output(users_prs, review_data, include_messages):
    out = []
    prs = get_prs(users_prs)
    longest_name = max(len(pr["name"]) for pr in prs)
    longest_base = max(len(pr["base"]) for pr in prs)
    longest_serial = max(len("%d" % pr["last_serial"]) for pr in prs)
    fmt = "{0:<%d} -> {1:<%d} at serial {2:>%d}{3}" % (longest_name, longest_base, longest_serial)
    for pr in prs:
        if pr["name"] in review_data:
            active = " (reviewing)"
        else:
            active = ""
        out.append(fmt.format(
            pr["name"], pr["base"], pr["last_serial"], active))
        if not include_messages:
            continue
        for state, by, message in zip(pr['states'], pr['by'], pr['messages']):
            out.append("    %s by %s:\n%s" % (
                state, by, textwrap.indent(message, "        ")))
        out.append("")
    return "\n".join(out)


def list_prs(hub, args):
    indexname = args.indexname
    current = hub.require_valid_current_with_index()
    index_url = current.get_index_url(indexname, slash=False)
    r = hub.http_api("get", index_url, fatal=False, type="indexconfig")
    ixconfig = r.result or {}
    hidden_states = set()
    if not args.all_states:
        hidden_states.add("approved")
    push_requests_allowed = ixconfig.get("push_requests_allowed", False)
    is_merge_index = ixconfig["type"] == "merge"
    if push_requests_allowed or is_merge_index:
        list_url = index_url.asdir().joinpath("+pr-list")
        r = hub.http_api("get", list_url, type="pr-list")
        index_data = r.result
    else:
        index_data = {}
    if not is_merge_index and not args.all_states:
        hidden_states.add("new")
    user = current.get_auth_user()
    if user:
        login_status = "logged in as %s" % user
    else:
        login_status = "not logged in"
    hub.info("current devpi index: %s (%s)" % (current.index, login_status))
    if user:
        user_url = current.get_user_url(indexname)
        list_url = user_url.asdir().joinpath("+pr-list")
        r = hub.http_api("get", list_url, type="pr-list")
        user_data = r.result
        if is_merge_index and not args.all_states:
            user_data.pop("new", None)
    else:
        user_data = {}
    pr_data = merge_pr_data(index_data, user_data)
    if not pr_data:
        hub.line("no pull requests")
        return
    for state in sorted(pr_data):
        if state in hidden_states:
            continue
        with devpi_pr_review_data(hub) as review_data:
            out = create_pr_list_output(
                pr_data[state], review_data, args.messages)
        hub.line("%s push requests" % state)
        hub.line(textwrap.indent(out, "    "))


def reject_pr_arguments(parser):
    """ reject push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "-m", "--message", action="store",
        help="Message to add on reject.")


def reject_pr(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    message = get_message(hub, args.message)
    hub.http_api("patch", indexinfos.url, [
        "states+=rejected",
        "messages+=%s" % message])


def review_pr_arguments(parser):
    """ start reviewing push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "-u", "--update", action="store_true",
        help="Update the serial of the review.")


def review_pr(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    (targetindex,) = indexinfos.ixconfig['bases']
    targeturl = hub.current.get_index_url(targetindex)
    r = hub.http_api("get", targeturl.asdir().joinpath("+pr-list"), type="pr-list")
    pending_prs = r.result.get("pending")
    if not pending_prs:
        hub.fatal("There are no pending PRs.")
    users_prs = pending_prs.get(indexinfos.user)
    for prs in users_prs:
        if prs["name"] == indexinfos.index:
            last_serial = prs["last_serial"]
            break
    else:
        hub.fatal("Could not find PR '%s'." % indexinfos.indexname)
    with devpi_pr_review_data(hub) as review_data:
        if indexinfos.indexname in review_data:
            if args.update:
                hub.info("Updated review of '%s' to serial %s" % (
                    indexinfos.indexname, last_serial))
            else:
                hub.warn("Already reviewing '%s' at serial %s" % (
                    indexinfos.indexname, review_data[indexinfos.indexname]))
                return
        else:
            hub.info(
                "Started review of '%s' at serial %s" % (
                    indexinfos.indexname, last_serial))
        review_data[indexinfos.indexname] = last_serial


def submit_pr_arguments(parser):
    """ submit push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "-m", "--message", action="store",
        help="Message to add on submit.")


def submit_pr(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    message = get_message(hub, args.message)
    hub.http_api("patch", indexinfos.url, [
        "states+=pending",
        "messages+=%s" % message])


def cancel_pr_arguments(parser):
    """ cancel push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "-m", "--message", action="store",
        help="Message to add on cancel.")


def cancel_pr(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    message = get_message(hub, args.message)
    hub.http_api("patch", indexinfos.url, [
        "states+=new",
        "messages+=%s" % message])


def delete_pr_arguments(parser):
    """ delete push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")


def delete_pr(hub, args):
    (name,) = args.name
    indexinfos = require_merge_index(hub, name)
    hub.http_api("delete", indexinfos.url)


@client_hookimpl
def devpiclient_subcommands():
    return [
        (new_pr_arguments, "new-pr", "devpi_pr.client:new_pr"),
        (submit_pr_arguments, "submit-pr", "devpi_pr.client:submit_pr"),
        (list_prs_arguments, "list-prs", "devpi_pr.client:list_prs"),
        (review_pr_arguments, "review-pr", "devpi_pr.client:review_pr"),
        (abort_pr_review_arguments, "abort-pr-review", "devpi_pr.client:abort_pr_review"),
        (approve_pr_arguments, "approve-pr", "devpi_pr.client:approve_pr"),
        (reject_pr_arguments, "reject-pr", "devpi_pr.client:reject_pr"),
        (cancel_pr_arguments, "cancel-pr", "devpi_pr.client:cancel_pr"),
        (delete_pr_arguments, "delete-pr", "devpi_pr.client:delete_pr")]
