#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2013
# Author: Mark Peng
# 
# Extended from Zdenko Podobný's work at: http://code.google.com/p/tesseract-ocr/wiki/APIExample
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import optparse
import ctypes
from ctypes import pythonapi, util, py_object
import io
import urllib.request
from PIL import Image
import traceback

"""
Get result string directly from tesseract C API
"""
class TesseactWrapper:
    def __init__(self, lang, libpath, tessdata):
        
        os.environ["DYLD_LIBRARY_PATH"] += os.pathsep + libpath
        libname = ctypes.util.find_library('tesseract')
        
        if libname is None:
            print("library name not deducted, exiting")
            exit(1)
        else:
            print("library name found: %s" % libname)

        try:
            self.tesseract = ctypes.cdll.LoadLibrary(libname)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            print(''.join('!! ' + line for line in lines))  # Log it or whatever here
            exit(1)

        self.tesseract.TessVersion.restype = ctypes.c_char_p
        tesseract_version = self.tesseract.TessVersion()

        # preprocessing version name 
        trimmed_version = tesseract_version
        if tesseract_version.count(b'.') > 1:
            trimmed_version = tesseract_version[:(tesseract_version.index(b'.') + 3)]

        # We need to check library version because libtesseract.so.3 is symlink
        # and can point to other version than 3.02
        if float(trimmed_version) < 3.02:
            print("Found tesseract-ocr library version %s." % tesseract_version)
            print("C-API is present only in version 3.02!")
            exit(2)

        self.tesseract.TessBaseAPICreate.restype = ctypes.POINTER(ctypes.c_void_p)
        self.api = self.tesseract.TessBaseAPICreate()

        rc = self.tesseract.TessBaseAPIInit3(self.api, tessdata.encode(), lang.encode())
        if (rc):
            self.tesseract.TessBaseAPIDelete(self.api)
            print("Could not initialize tesseract.\n")
            exit(3)

    def libraryFullPath(self, libpath):
        
        tesseractName = 'tesseract'
        
        if "DYLD_LIBRARY_PATH" not in os.environ:
            os.environ["DYLD_LIBRARY_PATH"] = ''
        
        os.environ["DYLD_LIBRARY_PATH"] += os.pathsep + libpath
        libname = ctypes.util.find_library(tesseractName)
    
        if libname is None:
            if os.name == "posix" and sys.platform != "darwin":
                expr = r'lib%s\.so' % re.escape(tesseractName)
                res = re.search(expr, os.listdir(libpath))
    
                if res:
                    return res.group(0)
    
        return libname

    def imageFileToString(self, filePath):
        
        # Running tesseract-ocr
        text_out = self.tesseract.TessBaseAPIProcessPages(self.api, filePath, None, 0)
        result_text = ctypes.string_at(text_out)
        print('Result: {}'.format(result_text))

        return result_text.replace("\n", "")

    def imageUrlToString(self, url, minWidth):

        # download image from url
#        file = io.StringIO(urllib.urlopen(url).read())

        with urllib.request.urlopen(url) as urlContent:
            file = io.BytesIO(urlContent.read())
                
        tmpImg = Image.open(file)

        # force resize to minimal width if the incoming image is too small for better precision
        width, height = tmpImg.size
        newHeight = height
        if width < minWidth:
            ratio = float(minWidth) / width
            newHeight = int(height * ratio)
            tmpImg = tmpImg.resize((minWidth, newHeight), Image.ANTIALIAS)
            print('resize image to ({}, {})'.format(str(minWidth), str(newHeight)))

        # transform data bytes to single dimensional array
        data = tmpImg.getdata()
        copyData = [0] * len(data) * 4
        for i in range(len(data)):
            for j in range(len(data[i])):
                cursor = i * 4 + j
                copyData[cursor] = data[i][j]

        # compute stride
        bytesPerLine = minWidth * 4

        # create a ctype ubyte array and copy data to it
        arrayLength = newHeight * minWidth * 4
        ubyteArray = (ctypes.c_ubyte * arrayLength)()
        for i in range(arrayLength):
            ubyteArray[i] = copyData[i]

        # call SetImage  
        self.tesseract.TessBaseAPISetImage.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.tesseract.TessBaseAPISetImage.restype = ctypes.c_void_p
        self.tesseract.TessBaseAPISetImage(self.api, ubyteArray, minWidth, newHeight, 4, bytesPerLine)

        # call GetUTF8Text
        self.tesseract.TessBaseAPIGetUTF8Text.restype = ctypes.c_char_p
        text_out =  self.tesseract.TessBaseAPIGetUTF8Text(self.api)
        result_text = ctypes.string_at(text_out)
  
        return result_text.replace(b"\n", b"")

def main():
    parser = optparse.OptionParser()
    parser.add_option('-l', '--lang', dest='lang', help='the targe language.')
    parser.add_option('-b', '--lib-path', dest='libPath', help='the absolute path of tesseract library.')
    parser.add_option('-d', '--tessdata-folder', dest='tessdata', help='the absolute path of tessdata folder containing language packs.')
    parser.add_option('-i', '--image-url', dest='imageUrl', help='the URL of image to do OCR.')
    parser.add_option('-m', '--min-width', dest='minWidth', help='the minmal width for image before running OCR. The program will try to resize the image to target width. (default: 150)')
    (options, args) = parser.parse_args()

    if not options.lang:   # if lang is not given
        parser.error('lang not given')
    if not options.libPath:   # if libPath is not given
        parser.error('lib-path not given')
    if not options.tessdata:   # if tessdata is not given
        parser.error('tessdata not given')
    if not options.imageUrl:   # if imageUrl is not given
        parser.error('image-url not given')
    if not options.minWidth:   # if minWidth is not given
        targetWidth = 150
    else:
        targetWidth = options.minWidth

    # call tesseract C API
    wrapper = TesseactWrapper(options.lang, options.libPath, options.tessdata)
    result_text = wrapper.imageUrlToString(options.imageUrl, targetWidth)
        
    print('Result: {}'.format(result_text.decode()))

    # Test
    # lang = "eng"
    # libpath = "/home/markpeng/local/lib"
    # tessdata = "/home/markpeng/temp/tesseract-ocr/"
    # wrapper = TesseactWrapper(lang, libpath, tessdata)
    # url = "http://price2.suning.cn/webapp/wcs/stores/prdprice/398956_9017_10000_9-1.png"
    # url = "http://price1.suning.cn/webapp/wcs/stores/prdprice/12973756_9017_10052_11-9.png"
    # wrapper.imageUrlToString(url, 150)

if __name__ == '__main__':
    main()
