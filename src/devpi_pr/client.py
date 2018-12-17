from pluggy import HookimplMarker


client_hookimpl = HookimplMarker("devpiclient")


def pr_arguments(parser):
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


def pr(hub, args):
    (name,) = args.name
    (target,) = args.target
    indexname = "+pr-" + name
    url = hub.current.get_index_url(indexname, slash=False)
    hub.http_api("put", url, dict(
        type="merge", bases=target))


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
        "state=pending",
        "messages+=%s" % message])


@client_hookimpl
def devpiclient_subcommands():
    return [
        (pr_arguments, "pr", "devpi_pr.client:pr"),
        (submit_pr_arguments, "submit-pr", "devpi_pr.client:submit_pr")]
