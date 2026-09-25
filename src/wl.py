# SPDX-FileCopyrightText: 2016 Silvio Peroni <essepuntato@gmail.com>
#
# SPDX-License-Identifier: ISC

__author__ = "essepuntato"
import logging
from datetime import datetime
from os import makedirs, path, sep

import web


class WebLogger:
    def __init__(self, name, log_dir, list_of_web_var=(), filter_request=()):
        self.l = logging.getLogger(name)
        self.vars = list_of_web_var
        self.filter = filter_request

        # Configure logger
        self.l.setLevel(logging.INFO)

        self.log_dir = log_dir
        self.month = None

        # Add a file handler if it is not set yet
        self.__set_file_handler()

    def __set_file_handler(self):
        cur_month = datetime.now().astimezone().strftime("%Y-%m")
        if self.month != cur_month:
            for fh in self.l.handlers:
                if isinstance(fh, logging.FileHandler):
                    self.l.removeHandler(fh)

            self.month = cur_month
            file_path = self.log_dir + sep + "oc-" + self.month + ".txt"
            if not path.exists(file_path):
                file_dir = path.dirname(file_path)
                if not path.exists(file_dir):
                    makedirs(file_dir)
                open(file_path, "a").close()

            file_handler = logging.FileHandler(file_path)
            log_formatter = logging.Formatter("%(asctime)s %(message)s")
            file_handler.setFormatter(log_formatter)
            file_handler.setLevel(logging.INFO)
            self.l.addHandler(file_handler)

    def mes(self):
        cur_message = ""
        must_be_filtered = False
        for var in self.vars:
            cur_value = str(web.ctx.env.get(var))
            if var in self.filter and cur_value in self.filter[var]:
                must_be_filtered = True
            cur_message += f"# {var}: {cur_value} "
        if not must_be_filtered:
            # Use the correct file handler
            self.__set_file_handler()
            self.l.info(cur_message)
