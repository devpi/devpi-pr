from pluggy import HookimplMarker
import json


client_hookimpl = HookimplMarker("devpiclient")


def new_pr_arguments(parser):
    """ create push request
    """
    parser.add_argument(
        "name", type=str, action="store", nargs=1,
        help="push request name")
    parser.add_argument(
        "pkgspec", metavar="pkgspec", type=str, nargs="*",
        default=None, action="store",
        help="releases in format 'name==version' which are added to "
             "this push request.")
    parser.add_argument(
        "target", metavar="TARGETSPEC", type=str, nargs=1,
        action="store",
        help="target index of form 'USER/NAME'")


def new_pr(hub, args):
    (name,) = args.name
    (target,) = args.target
    indexname = "+pr-" + name
    url = hub.current.get_index_url(indexname, slash=False)
    hub.http_api("put", url, dict(
        type="merge", bases=target,
        states=["new"], messages=["New push request"]))


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
    message = args.message
    indexname = "+pr-" + name
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


def list_prs(hub, args):
    indexname = args.indexname
    url = hub.current.get_index_url(indexname).asdir().joinpath("+pr-list")
    r = hub.http_api("get", url, type="pr-list")
    print(json.dumps(r.result))


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
    message = args.message
    indexname = "+pr-" + name
    url = hub.current.get_index_url(indexname, slash=False)
    hub.http_api("patch", url, [
        "states+=pending",
        "messages+=%s" % message])


@client_hookimpl
def devpiclient_subcommands():
    return [
        (new_pr_arguments, "new-pr", "devpi_pr.client:new_pr"),
        (approve_pr_arguments, "approve-pr", "devpi_pr.client:approve_pr"),
        (list_prs_arguments, "list-prs", "devpi_pr.client:list_prs"),
        (submit_pr_arguments, "submit-pr", "devpi_pr.client:submit_pr")]
