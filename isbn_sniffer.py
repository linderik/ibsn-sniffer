#!/usr/bin/python

import sys
import os
import re
import shutil
import isbnlib
import argparse
from zipfile import ZipFile
from subprocess import Popen, PIPE
from PyPDF2 import PdfFileReader

# PyPDF2 warnings for PDF bypassed
import warnings
warnings.filterwarnings("ignore")

tmp_purku_dir = '/tmp/epub-purku/'
pdftotext_exec = '/usr/bin/pdftotext -q'

# Returns ISBN from EPUB or PDF, without dashes if not possible to interpret the dashed form
# EPUB case: finds first valid ISBN match from OPF-file
# PDF case: finds last valid ISBN from PDF-file with (*pdf*) following after the ISBN
# PDF: first 6 and last 4 pages are searched
# With paramater -c checks filename for ISBN and returns it if found
# With parameter --crop cuts first 10 chars off from the filename (varsta-specific use)
# With parameter --all returns all matches (from PDF only)
# -----------------------------------------------------------

isbn_pattern = '(' + (r'\d *((-|\xe2\x80\x93) *)?')*9 + \
      (r'(\d *((-|\xe2\x80\x93) *)?)?')*3  + '[0-9X])'


def main(filename,
         compare_filename=False,
         crop_timestamp=False,
         return_all=False):

    if not filename.lower().endswith(('.pdf', '.epub')):
        print >> sys.stderr, 'Cannot handle other than PDF and EPUB files: ' + filename
        retval = 1
        return retval

    isbn = get_isbn(filename, compare_filename, crop_timestamp, return_all)

    if isbn:
        print isbn
        retval = 0
    else:
        print >> sys.stderr, 'Did not find ISBN for: ' + filename
        retval = 1
    return retval


def get_isbn(filename, compare_filename, crop_timestamp, return_all):

    if compare_filename:
        filename_isbn = get_isbn_from_filename(filename, crop_timestamp)
    else:
        filename_isbn = None

    # With --all switch gather all isbns (EPUB doesn't return all because metadata has only EPUB ISBN)
    if return_all:
        isbns = {}
        if filename_isbn:
            isbns.update({"Filename ISBN": filename_isbn})
        if '.epub' in filename:
            isbns.update({"EPUB ISBN": extract_isbn_from_epub(filename)})
        elif '.pdf' in filename:
            isbns.update(
                {"PDF ISBNS": extract_isbn_from_pdf(filename, return_all)})
        return isbns

    # Returns isbn if found in filename
    if filename_isbn:
        return filename_isbn

    isbn = None

    if '.epub' in filename.lower():
        isbn = extract_isbn_from_epub(filename)
    elif '.pdf' in filename.lower():
        isbn = extract_isbn_from_pdf(filename)

    return isbn


def get_isbn_from_filename(filename, crop_timestamp):
    if crop_timestamp:
        filename = filename.split("/")
        filename = filename[len(filename) - 1]
        # Remove timestamp
        filename = filename[10:]

    isbns = re.findall(isbn_pattern, filename)

    # Check hits for valid ISBN, return last one
    return check_isbns(isbns, "last")


def extract_isbn_from_epub(filename):
    try:
        os.path.exists(tmp_purku_dir) or os.mkdir(tmp_purku_dir)
        zip = ZipFile(filename)
        zip.extractall(tmp_purku_dir)
    except:
        pass
        print >> sys.stderr, "Error occurred when trying to extract " + filename

    opf_files = []
    isbns = None

    #Searches for .opf files which are the metadata files for EPUB
    for root, dirs, files in os.walk(tmp_purku_dir):
        for filename in files:
            if filename.lower().endswith('.opf'):
                opf_files.append(os.path.join(root, filename))

    for file in opf_files:
        with open(file, 'r') as myfile:
            opf_string = myfile.read().replace('\n', '')
            isbns = re.findall(isbn_pattern, opf_string)

    shutil.rmtree(tmp_purku_dir)

    isbn = None

    # Check hits for valid ISBN, return first one
    if isbns is not None:
        isbn = check_isbns(isbns, "first")

    return isbn


def extract_isbn_from_pdf(filename, return_all=False):

    # 6 first pages
    text = get_pdf_text(filename, (0, 6))

    no_pages = get_no_pages(filename)
    if no_pages is not None:
        # add 4 last pages
        text = text + get_pdf_text(filename, (no_pages - 4, no_pages))

    isbn = None

    if text:
        if return_all:
            # Matches all ISBN "XXXXXXXXXXXXX (ANY)"
            pdf_only_pattern = r' *\( *[\w.]+ *\)'
            isbns = re.findall(isbn_pattern + pdf_only_pattern, text,
                               re.IGNORECASE)
            return check_isbns(isbns, "all")

        # Pdf only-pattern "XXXXXXXXXXXXX (PDF)" can be found many times (different versions)
        pdf_only_pattern = r' *\( *pdf *\)'

        isbns = re.findall(isbn_pattern + pdf_only_pattern, text,
                           re.IGNORECASE)

        # If no ISBN "XXXXXXXXXXXXX (PDF)" matches, check without "(PDF)", for cases with probably only 1 ISBN
        if not isbns:
            isbns = re.findall(isbn_pattern, text, re.IGNORECASE)

        # Check hits for valid ISBN, return last one (later version presumed to be last in the document)
        isbn = check_isbns(isbns, "last")

    return isbn


def check_isbns(isbns, return_value="last"):
    isbn = None
    all_isbns = []

    # Check the validity of regex matches
    for i in isbns:
        if isbnlib.is_isbn10(i[0]) or isbnlib.is_isbn13(i[0]):
            if return_value == "last":
                isbn = isbnlib.mask(i[0], separator='-')
            elif return_value == "first":
                return isbnlib.mask(i[0], separator='-')
            elif return_value == "all":
                all_isbns.append(isbnlib.mask(i[0], separator='-'))
            else:
                return None
        else:
            #print >>sys.stderr, i[0] + " is not valid ISBN"
            continue

    return isbn if return_value != "all" else all_isbns


def get_no_pages(filename):
    try:
        pdf = PdfFileReader(open(filename, 'rb'))
        num_pages = pdf.getNumPages()
        return num_pages
    except:
        sys.stderr.write("Cannot read (or get number of pages in) file: " +
                         filename + "\n")


def get_pdf_text(filename, range):
    cmd = pdftotext_exec
    # UNIX:
    return Popen(cmd + " -f " + str(range[0]) + " -l " + str(range[1]) +
                 " \"" + filename + "\" -",
                 stdout=PIPE,
                 shell=True).communicate()[0]


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="ISBN Sniffer",
        usage="Usage: %s [-c --crop --all] file\n" % sys.argv[0])
    parser.add_argument('input_file',
                        action='store',
                        help="Specify the input file to be sniffed")
    parser.add_argument('--crop',
                        action="store_true",
                        dest="CROP",
                        default=False,
                        help="Crop 10 characters from filename")
    parser.add_argument("-c",
                        action="store_true",
                        dest="COMPARE",
                        default=False,
                        help="Compare filename")
    parser.add_argument("--all",
                        action="store_true",
                        dest="ALL",
                        default=False,
                        help="Return all matches")
    args = parser.parse_args()

    if args.input_file:
        sys.exit(main(args.input_file, args.COMPARE, args.CROP, args.ALL))
    else:
        sys.stderr.write("Usage: %s [-c --crop --all] file\n" % sys.argv[0])
