""" Verification/Validation
"""
from lxml import etree

from sii.lib import validation as validate

from .helpers import read_xml


def handle(args, config):
    if args['signature']:
        validate_signature(args, config)
    if args['schema']:
        validate_schema(args, config)
    if args['caf']:
        validate_caf(args, config)


def validate_signature(args, config):
    for xml_fpath in args['<infile>']:
        xml = read_xml(xml_fpath)

        outcomes = {
            True:  "Good Signature.",
            False: "Bad Signature."
        }

        results = validate.validate_signatures(xml)
        for uri, validity in results:
            print("{0}: {1}: {2}".format(xml_fpath, uri, outcomes[validity]))


def validate_schema(args, config):
    xml_schema = None
    if args['--xsd']:
        with open(args['--xsd'], 'rb') as fh:
            xml_schema = etree.parse(fh)

    for xml_fpath in args['<infile>']:
        xml      = read_xml(xml_fpath)
        path_str = xml_fpath + ":"

        try:
            validate.validate_schema(xml, xml_schema)
        except etree.DocumentInvalid as exc:
            print(path_str, "Bad Schema. " + str(exc))
        else:
            print(path_str, "Good Schema.")


def validate_caf(args, config):
    raise NotImplementedError
