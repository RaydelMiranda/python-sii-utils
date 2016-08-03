""" SII Interaction and Convenience Utilities.

Usage:
    sii [options] <command> [<args>...]

Commands:
    dte  Tools for generation, manipulation and instrospection of SII documents.
    xml  Tools for manipulation and checking of XML files according to SII schemas.
    pdf  Tools for the PDF subsystem; creation of PDF's from XML's or printing them.
    ws   Tools for interactions with the SII Web Services, their protocols etc.
    xch  Tools for mailing/exchange of DTE's between Emitters.
    lcv  Tools for introspection and manipulation of LC's and LV's.

    help     This message.
    version  Display version number.

Common Options:
    --config <cfg>  # Configuration file to read from. [default: ~/.config/sii/cfg_utils.yml]
    --debug         # Drop to post-mortem debugging instead of failing with a message.
    --help          # This message.
    --version       # Display version number.
"""
import pdb
import sys
import traceback

import docopt
import pkg_resources

from . import cmd_dte
from . import cmd_lcv
from . import cmd_pdf
from . import cmd_ws
from . import cmd_xch
from . import cmd_xml

from .config import Configuration

DEFAULT_CONFIG_PATH = '/usr/share/doc/python3-sii-utils/templ_config.yml'
VERSION             = pkg_resources.get_distribution("python-sii-utils").version

ACTIONS = {
    'dte': cmd_dte,
    'lcv': cmd_lcv,
    'pdf': cmd_pdf,
    'ws' : cmd_ws,
    'xch': cmd_xch,
    'xml': cmd_xml
}


def cmd(args, config):
    module = ACTIONS.get(args['<command>'], None)

    if args['<command>'] == 'help':
        print(__doc__)
    elif args['<command>'] == 'version':
        print(VERSION)
    else:
        if module is None:
            print("Unknown Command: {0}".format(args['<command>']), file=sys.stderr)
        else:
            argv = [args['<command>']] + args['<args>']
            return module.handle(config, args, argv)


def main():
    args = docopt.docopt(__doc__, options_first=True, version=VERSION)

    try:
        config = Configuration(cfg_path=args['--config'], cfg_templ=DEFAULT_CONFIG_PATH)
        cmd(args, config)
    except KeyboardInterrupt:
        _error_handling(args, "")
    except Exception as exc:
        _error_handling(args, "Failed with message (introspect with --debug): \"{0}\"".format(str(exc)))


def _error_handling(args, msg):
    if args['--debug']:
        traceback.print_exc()
        pdb.post_mortem()
    else:
        print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
