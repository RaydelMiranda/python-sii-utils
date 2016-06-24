""" Various Convencience Functions
"""
import re
import sys
import os.path as path

from lxml import etree


__all__ = [
    'read_xml',
    'read_xmls',
    'write_xml',
    'print_xml',
    'print_stderr',
    'print_exit',
    'stack_extension'
]

XML_DECL = lambda enc: b'<?xml version="1.0" encoding="' + bytes(enc, enc) + b'"?>'


def read_xml(xml_fpath):
    with open(xml_fpath, 'rb') as fh:
        tree = etree.parse(fh)
        root = tree.getroot()

        return root


def read_xmls(xml_fpaths):
    for xml_fpath in xml_fpaths:
        yield read_xml(xml_fpath)


def write_xml(xml, fpath, end='\n', encoding='ISO-8859-1', append=False):
    mode = ''

    if append:
        mode = 'ab'
    else:
        mode = 'wb'

    with open(fpath, mode) as fh:
        bytebuff = etree.tostring(
            xml,
            pretty_print    = True,
            method          = 'xml',
            encoding        = encoding,
            xml_declaration = False
        )

        if end != '\n':
            decoded  = str(bytebuff, encoding)
            modified = re.sub('\n', end, decoded)
            bytebuff = bytes(modified, encoding)

        fh.write(XML_DECL(encoding) + bytes(end, encoding) + bytebuff)


def print_xml(xml, file=sys.stdout, end='\n', encoding='UTF-8'):
    bytebuff = etree.tostring(
        xml,
        pretty_print    = True,
        method          = 'xml',
        encoding        = encoding,
        xml_declaration = False
    )

    encoded_end = bytes(end, encoding)
    file.buffer.write(XML_DECL(encoding) + encoded_end + bytebuff + encoded_end)


def print_stderr(string):
    print(string, file=sys.stderr)


def print_exit(string, code=0):
    print_stderr(string)
    sys.exit(code)


def stack_extension(fpath, ext):
    base, ext_old = path.splitext(fpath)

    return "{base}.{stacked}{ext}".format(
        base    = base,
        stacked = ext,
        ext     = ext_old
    )
