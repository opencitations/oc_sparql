# SPDX-FileCopyrightText: 2026 Mario Petrella <mario.petrella@unibo.it>
#
# SPDX-License-Identifier: ISC

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse as urlparse
from collections.abc import Callable
from typing import cast

import requests
import web
from pyparsing import ParseException
from rdflib.plugins.sparql.parser import parseUpdate

# Load the configuration file
with open("conf.json") as f:
    c = json.load(f)


# Docker ENV variables
env_config = {
    "log_dir": os.getenv("LOG_DIR", c["log_dir"]),
    "base_url": os.getenv("BASE_URL", c["base_url"]),
    "sparql_endpoint_index": os.getenv(
        "SPARQL_ENDPOINT_INDEX", c["sparql_endpoint_index"]
    ),
    "sparql_endpoint_meta": os.getenv(
        "SPARQL_ENDPOINT_META", c["sparql_endpoint_meta"]
    ),
    "sync_enabled": os.getenv("SYNC_ENABLED", "false").lower() == "true",
}


active = {
    "corpus": "datasets",
    "index": "datasets",
    "meta": "datasets",
    "coci": "datasets",
    "doci": "datasets",
    "poci": "datasets",
    "croci": "datasets",
    "ccc": "datasets",
    "oci": "tools",
    "intrepid": "tools",
    "api": "querying",
    "sparql": "querying",
    "search": "querying",
}

# URL Mapping
urls = (
    "/",
    "Main",
    "/static/(.*)",
    "Static",
    "/health",
    "Health",
    "/meta",
    "SparqlMeta",
    "/favicon.ico",
    "Favicon",
    "/index",
    "SparqlIndex",
    "/index/description",
    "IndexDescription",
    "/meta/description",
    "MetaDescription",
    "/.well-known/void",
    "WellKnownVoid",
)

# Set the web logger
# web_logger = WebLogger(env_config["base_url"], env_config["log_dir"], [
#     "HTTP_X_FORWARDED_FOR", # The IP address of the client
#     "REMOTE_ADDR",          # The IP address of internal balancer
#     "HTTP_USER_AGENT",      # The browser type of the visitor
#     "HTTP_REFERER",         # The URL of the page that called your program
#     "HTTP_HOST",            # The hostname of the page being attempted
#     "REQUEST_URI",          # The interpreted pathname of the requested document
#                             # or CGI (relative to the document root)
#     "HTTP_AUTHORIZATION",   # Access token
#     ],
#     # comment this line only for test purposes
#      {"REMOTE_ADDR": ["130.136.130.1", "130.136.2.47", "127.0.0.1"]}
# )

render = web.template.render(
    c["html"],
    globals={
        "str": str,
        "isinstance": isinstance,
        "render": lambda *args, **kwargs: cast(Callable[..., object], render)(
            *args, **kwargs
        ),
    },
)

# App Web.py
app = web.application(urls, globals())

# WSGI application
application = app.wsgifunc()


def sync_static_files():
    """
    Function to synchronize static files using sync_static.py
    """
    try:
        print("Starting static files synchronization...")
        subprocess.run([sys.executable, "sync_static.py", "--auto"], check=True)
        print("Static files synchronization completed")
    except subprocess.CalledProcessError as e:
        print(f"Error during static files synchronization: {e}")


# Process favicon.ico requests
class Favicon:
    def GET(self):
        is_https = (
            web.ctx.env.get("HTTP_X_FORWARDED_PROTO") == "https"
            or web.ctx.env.get("HTTPS") == "on"
            or web.ctx.env.get("SERVER_PORT") == "443"
        )
        protocol = "https" if is_https else "http"
        raise web.seeother(f"{protocol}://{web.ctx.host}/static/favicon.ico")


class Health:
    """Lightweight health check endpoint for Kubernetes probes"""

    def GET(self):
        web.header("Content-Type", "application/json")
        return '{"status": "ok"}'


class Header:
    def GET(self):
        current_subdomain = web.ctx.host.split(".")[0].lower()
        render_header = cast(Callable[..., object], render.header)
        return render_header(sp_title="", current_subdomain=current_subdomain)


class Sparql:
    def __init__(self, sparql_endpoint, sparql_endpoint_title, yasqe_sparql_endpoint):
        self.sparql_endpoint = sparql_endpoint
        self.sparql_endpoint_title = sparql_endpoint_title
        self.yasqe_sparql_endpoint = yasqe_sparql_endpoint
        self.collparam = ["query"]

    def GET(self):
        # web_logger.mes()
        content_type = web.ctx.env.get("CONTENT_TYPE")
        return self.__run_query_string(
            self.sparql_endpoint_title, web.ctx.env.get("QUERY_STRING"), content_type
        )

    def POST(self):
        content_type = web.ctx.env.get("CONTENT_TYPE")
        cur_data = web.data().decode("utf-8")

        if "application/x-www-form-urlencoded" in content_type:
            return self.__run_query_string(
                active["sparql"], cur_data, True, content_type
            )
        elif "application/sparql-query" in content_type:
            isupdate = None
            isupdate, _ = self.__is_update_query(cur_data)
            if not isupdate:
                return self.__contact_tp(cur_data, True, content_type)
            else:
                raise web.HTTPError(
                    "403 ",
                    {"Content-Type": "text/plain"},
                    "SPARQL Update queries are not permitted.",
                )
        else:
            raise web.redirect("/")

    def __contact_tp(self, data, is_post, content_type):
        accept = web.ctx.env.get("HTTP_ACCEPT")
        if accept is None or accept == "*/*" or accept == "":
            accept = "application/sparql-results+xml"
        if is_post:
            req = requests.post(
                self.sparql_endpoint,
                data=data,
                headers={"content-type": content_type, "accept": accept},
            )
        else:
            req = requests.get(
                f"{self.sparql_endpoint}?{data}",
                headers={"content-type": content_type, "accept": accept},
            )

        if req.status_code == 200:
            web.header("Access-Control-Allow-Origin", "*")
            web.header("Access-Control-Allow-Credentials", "true")
            if req.headers["content-type"] == "application/json":
                web.header("Content-Type", "application/sparql-results+json")
            else:
                web.header("Content-Type", req.headers["content-type"])
            # web_logger.mes()
            req.encoding = "utf-8"
            return req.text
        else:
            raise web.HTTPError(
                str(req.status_code) + " ",
                {"Content-Type": req.headers["content-type"]},
                req.text,
            )

    def __is_update_query(self, query):
        query = re.sub(r"^\s*#.*$", "", query, flags=re.MULTILINE)
        query = "\n".join(line for line in query.splitlines() if line.strip())
        try:
            parseUpdate(query)
            return True, "UPDATE query not allowed"
        except ParseException:
            return False, query

    def __run_query_string(
        self,
        active,
        query_string,
        is_post=False,
        content_type="application/x-www-form-urlencoded",
    ):
        parsed_query = urlparse.parse_qs(query_string)
        current_subdomain = web.ctx.host.split(".")[0].lower()
        if query_string is None or query_string.strip() == "":
            # web_logger.mes()
            web.header(
                "Link",
                f'</{self.sparql_endpoint_title}/description>; rel="describedby"',
            )
            render_endpoint = cast(
                Callable[..., object], getattr(render, self.sparql_endpoint_title)
            )
            return render_endpoint(
                active=active,
                sp_title=self.sparql_endpoint_title,
                sparql_endpoint=self.yasqe_sparql_endpoint,
                render=render,
                current_subdomain=current_subdomain,
            )
        for k in self.collparam:
            if k in parsed_query:
                query = parsed_query[k][0]
                isupdate = None
                isupdate, _ = self.__is_update_query(query)

                if isupdate != None:
                    if isupdate:
                        raise web.HTTPError(
                            "403 ",
                            {"Content-Type": "text/plain"},
                            "SPARQL Update queries are not permitted.",
                        )
                    else:
                        return self.__contact_tp(query_string, is_post, content_type)

        raise web.HTTPError(
            "408", {"Content-Type": "text/plain"}, "Not a valid request"
        )


class Main:
    def GET(self):
        # web_logger.mes()
        current_subdomain = web.ctx.host.split(".")[0].lower()
        render_sparql = cast(Callable[..., object], render.sparql)
        return render_sparql(
            active="",
            sp_title="",
            sparql_endpoint="",
            current_subdomain=current_subdomain,
            render=render,
        )


class SparqlIndex(Sparql):
    def __init__(self):
        Sparql.__init__(self, env_config["sparql_endpoint_index"], "index", "/index")


class SparqlMeta(Sparql):
    def __init__(self):
        Sparql.__init__(self, env_config["sparql_endpoint_meta"], "meta", "/meta")


class Static:
    def GET(self, name):
        """Serve static files"""
        static_dir = "static"
        file_path = os.path.join(static_dir, name)

        if not os.path.exists(file_path):
            raise web.notfound()

        # Content types
        ext = os.path.splitext(name)[1]
        content_types = {
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".ttl": "text/turtle",
            ".jsonld": "application/ld+json",
            ".rdf": "application/rdf+xml",
            ".nt": "application/n-triples",
        }

        web.header("Content-Type", content_types.get(ext, "application/octet-stream"))

        with open(file_path, "rb") as f:
            return f.read()


_SD_TYPES = {
    "text/turtle": (".ttl", "text/turtle; charset=utf-8"),
    "application/ld+json": (".jsonld", "application/ld+json; charset=utf-8"),
    "application/rdf+xml": (".rdf", "application/rdf+xml; charset=utf-8"),
    "application/n-triples": (".nt", "application/n-triples; charset=utf-8"),
    "text/html": (".html", "text/html; charset=utf-8"),
}
_SD_DEFAULT_EXT = ".ttl"
_SD_DEFAULT_CT = "text/turtle; charset=utf-8"


def _parse_accept(accept):
    media_ranges = []
    for position, value in enumerate(accept.split(",")):
        media_type, *parameters = (part.strip() for part in value.split(";"))
        quality = 1.0
        for parameter in parameters:
            name, parameter_value = parameter.split("=", 1)
            if name.lower() == "q":
                quality = float(parameter_value)
        resource_type, resource_subtype = media_type.lower().split("/", 1)
        specificity = int(resource_type != "*") + int(resource_subtype != "*")
        media_ranges.append(
            (resource_type, resource_subtype, quality, specificity, -position)
        )
    return media_ranges


def _select_sd_type(accept):
    if accept is None or accept.strip() == "":
        return _SD_DEFAULT_EXT, _SD_DEFAULT_CT

    media_ranges = _parse_accept(accept)
    representations = []
    for server_preference, (media_type, representation) in enumerate(_SD_TYPES.items()):
        resource_type, resource_subtype = media_type.split("/", 1)
        matches = [
            (quality, specificity, client_preference)
            for (
                accepted_type,
                accepted_subtype,
                quality,
                specificity,
                client_preference,
            ) in media_ranges
            if accepted_type in ("*", resource_type)
            and accepted_subtype in ("*", resource_subtype)
        ]
        if matches:
            quality, specificity, _ = max(matches, key=lambda item: (item[1], item[2]))
            if quality > 0:
                representations.append(
                    (quality, specificity, -server_preference, representation)
                )

    if not representations:
        raise web.notacceptable()
    return max(representations)[3]


def _serve_sd_file(base_name):
    accept = web.ctx.env.get("HTTP_ACCEPT")
    ext, ct = _select_sd_type(accept)
    file_path = os.path.join("static", "service-descriptions", f"{base_name}{ext}")
    if not os.path.exists(file_path):
        raise web.notfound()
    web.header("Content-Type", ct)
    web.header("Access-Control-Allow-Origin", "*")
    web.header("Vary", "Accept")
    with open(file_path, "rb") as f:
        return f.read()


class IndexDescription:
    def GET(self):
        return _serve_sd_file("index")


class MetaDescription:
    def GET(self):
        return _serve_sd_file("meta")


class WellKnownVoid:
    def GET(self):
        return _serve_sd_file("void")


# Run the application on localhost for testing/development
if __name__ == "__main__":
    # Add startup log
    print("Starting SPARQL OpenCitations web application...")
    print(f"Configuration: Base URL={env_config['base_url']}")
    print(f"Sync enabled: {env_config['sync_enabled']}")

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="SPARQL OpenCitations web application")
    parser.add_argument(
        "--sync-static",
        action="store_true",
        help="synchronize static files at startup (for local testing or development)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="port to run the application on (default: 8080)",
    )

    args = parser.parse_args()
    print(f"Starting on port: {args.port}")

    if args.sync_static or env_config["sync_enabled"]:
        # Run sync if either --sync-static is provided (local testing)
        # or SYNC_ENABLED=true (Docker environment)
        print("Static sync is enabled")
        sync_static_files()
    else:
        print("Static sync is disabled")

    print("Starting web server...")
    # Set the port for web.py
    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", args.port))
