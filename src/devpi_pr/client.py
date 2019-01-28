from devpi_common.metadata import parse_requirement
from pluggy import HookimplMarker
from tempfile import NamedTemporaryFile
from subprocess import call
import os
import textwrap
import traceback


client_hookimpl = HookimplMarker("devpiclient")


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
        lines = tf.read().decode('utf-8').splitlines()
        msg = '\n'.join(x for x in lines if not x.strip().startswith('#'))
        msg = msg.strip()
        if msg:
            return msg
    hub.fatal("A message is required.")


def full_indexname(hub, prname):
    if '/' in prname:
        try:
            user, prname = prname.split('/')
        except ValueError:
            hub.fatal("Invalid index name")
    else:
        user = hub.current.get_auth_user()
    if not prname.startswith('+pr-'):
        prname = "+pr-%s" % prname
    return "%s/%s" % (user, prname)


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


def approve_pr_arguments(parser):
    """ approve push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "serial", type=str, action="store", nargs=1,
        help="push request serial")
    parser.add_argument(
        "-m", "--message", action="store",
        help="Message to add on submit.")


def approve_pr(hub, args):
    (name,) = args.name
    (serial,) = args.serial
    message = get_message(hub, args.message)
    indexname = full_indexname(hub, name)
    url = hub.current.get_index_url(indexname, slash=False)
    hub.http_api(
        "patch", url, [
            "states+=approved",
            "messages+=%s" % message],
        headers={'X-Devpi-PR-Serial': serial})


def list_prs_arguments(parser):
    """ list push requests
    """
    parser.add_argument(
        "indexname", type=str, action="store", nargs="?",
        help="index name, specified as NAME or USER/NAME.  If no index "
             "is specified use the current index")


def get_name_serials(users_prs):
    result = []
    for user, prs in users_prs.items():
        for pr in prs:
            name = "%s/%s" % (user, pr['name'])
            result.append((name, pr['base'], pr['last_serial']))
    return sorted(result)


def create_pr_list_output(users_prs):
    out = []
    name_serials = get_name_serials(users_prs)
    longest_name = max(len(x[0]) for x in name_serials)
    longest_base = max(len(x[1]) for x in name_serials)
    longest_serial = max(len("%d" % x[2]) for x in name_serials)
    fmt = "{0:<%d} -> {1:<%d} {2:>%d}" % (longest_name, longest_base, longest_serial + 3)
    for name, base, serial in get_name_serials(users_prs):
        out.append(fmt.format(name, base, serial))
    return out


def list_prs(hub, args):
    indexname = args.indexname
    url = hub.current.get_index_url(indexname).asdir().joinpath("+pr-list")
    r = hub.http_api("get", url, type="pr-list")
    for state in sorted(r.result):
        out = create_pr_list_output(r.result[state])
        print("%s push requests" % state)
        print("\n".join("    %s" % x for x in out))


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
    hub.requires_login()
    current = hub.require_valid_current_with_index()
    (name,) = args.name
    message = get_message(hub, args.message)
    indexname = full_indexname(hub, name)
    url = current.get_index_url(indexname, slash=False)
    hub.http_api("patch", url, [
        "states+=rejected",
        "messages+=%s" % message])


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
    hub.requires_login()
    current = hub.require_valid_current_with_index()
    (name,) = args.name
    message = get_message(hub, args.message)
    indexname = full_indexname(hub, name)
    url = current.get_index_url(indexname, slash=False)
    hub.http_api("patch", url, [
        "states+=pending",
        "messages+=%s" % message])


def delete_pr_arguments(parser):
    """ delete push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")


def delete_pr(hub, args):
    hub.requires_login()
    current = hub.require_valid_current_with_index()
    (name,) = args.name
    indexname = full_indexname(hub, name)
    url = current.get_index_url(indexname, slash=False)
    hub.http_api("delete", url)


@client_hookimpl
def devpiclient_subcommands():
    return [
        (new_pr_arguments, "new-pr", "devpi_pr.client:new_pr"),
        (approve_pr_arguments, "approve-pr", "devpi_pr.client:approve_pr"),
        (list_prs_arguments, "list-prs", "devpi_pr.client:list_prs"),
        (reject_pr_arguments, "reject-pr", "devpi_pr.client:reject_pr"),
        (submit_pr_arguments, "submit-pr", "devpi_pr.client:submit_pr"),
        (delete_pr_arguments, "delete-pr", "devpi_pr.client:delete_pr")]
