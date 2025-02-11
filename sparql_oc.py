import web
import os
import json
from src.wl import WebLogger
import requests
import urllib.parse as urlparse
import re
from urllib.parse import parse_qs
from rdflib.plugins.sparql.parser import parseUpdate
import subprocess
import sys
import argparse

# Docker ENV variables
sparql_config = {
    "sparql_base_url": os.getenv("SPARQL_BASE_URL", "sparql.opencitations.net"),
    "sparql_endpoint_index": os.getenv("SPARQL_ENDPOINT_INDEX", "http://qlever-service.default.svc.cluster.local:7011"),
    "sparql_endpoint_meta": os.getenv("SPARQL_ENDPOINT_META", "http://virtuoso-service.default.svc.cluster.local:8890/sparql"),
    "sparql_sync_enabled": os.getenv("SPARQL_SYNC_ENABLED", "false").lower() == "true"
}

# Load the configuration file
with open("conf.json") as f:
    c = json.load(f)

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
    "search": "querying"
}

# URL Mapping
urls = (
    "/", "Main",
    "/meta", "SparqlMeta",
    '/favicon.ico', 'Favicon',
    "/index", "SparqlIndex"
)

# Set the web logger
web_logger = WebLogger("sparql.opencitations.net", c["log_dir"], [
    "REMOTE_ADDR",        # The IP address of the visitor
    "HTTP_USER_AGENT",    # The browser type of the visitor
    "HTTP_REFERER",       # The URL of the page that called your program
    "HTTP_HOST",          # The hostname of the page being attempted
    "REQUEST_URI",        # The interpreted pathname of the requested document
                          # or CGI (relative to the document root)
    "HTTP_AUTHORIZATION",  # Access token
    ],
    # comment this line only for test purposes
     {"REMOTE_ADDR": ["130.136.130.1", "130.136.2.47", "127.0.0.1"]}
)

render = web.template.render(c["html"], globals={
    'str': str,
    'isinstance': isinstance,
    'render': lambda *args, **kwargs: render(*args, **kwargs)
})

# App Web.py
app = web.application(urls, globals())

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
    except Exception as e:
        print(f"Unexpected error during synchronization: {e}")


# Process favicon.ico requests
class Favicon:
    def GET(self): 
        raise web.seeother("/static/favicon.ico")

class Header:
    def GET(self):
        current_subdomain = web.ctx.host.split('.')[0].lower()
        return render.header(sp_title="", current_subdomain=current_subdomain)

class Sparql:
    def __init__(self, sparql_endpoint, sparql_endpoint_title, yasqe_sparql_endpoint):
        self.sparql_endpoint = sparql_endpoint
        self.sparql_endpoint_title = sparql_endpoint_title
        self.yasqe_sparql_endpoint = yasqe_sparql_endpoint
        self.collparam = ["query"]

    def GET(self):
        web_logger.mes()
        content_type = web.ctx.env.get('CONTENT_TYPE')
        return self.__run_query_string(self.sparql_endpoint_title, web.ctx.env.get("QUERY_STRING"), content_type)

    def POST(self):
        content_type = web.ctx.env.get('CONTENT_TYPE')
        cur_data = web.data().decode("utf-8")

        if "application/x-www-form-urlencoded" in content_type:
            return self.__run_query_string(active["sparql"], cur_data, True, content_type)
        elif "application/sparql-query" in content_type:
            isupdate = None
            isupdate, sanitizedQuery = self.__is_update_query(cur_data)
            if not isupdate:
                return self.__contact_tp(sanitizedQuery, True, content_type)
            else:
                raise web.HTTPError(
                    "403 ",
                    {"Content-Type": "text/plain"},
                    "SPARQL Update queries are not permitted."
                )
        else:
            raise web.redirect("/")

    def __contact_tp(self, data, is_post, content_type):
        accept = web.ctx.env.get('HTTP_ACCEPT')
        if accept is None or accept == "*/*" or accept == "":
            accept = "application/sparql-results+xml"
        if is_post:
            req = requests.post(self.sparql_endpoint, data={'query': data},
                              headers={'content-type': content_type, "accept": accept})
        else:
            req = requests.get("%s?query=%s" % (self.sparql_endpoint, data),
                             headers={'content-type': content_type, "accept": accept})

        if req.status_code == 200:
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Access-Control-Allow-Credentials', 'true')
            web.header('Content-Type', req.headers["content-type"])
            web_logger.mes()
            req.encoding = "utf-8"
            return req.text
        else:
            raise web.HTTPError(
                str(req.status_code)+" ", {"Content-Type": req.headers["content-type"]}, req.text)

    def __is_update_query(self, query):
        query = re.sub(r'^\s*#.*$', '', query, flags=re.MULTILINE)
        query = '\n'.join(line for line in query.splitlines() if line.strip()) 
        try:
            parseUpdate(query)
            return True, 'UPDATE query not allowed'
        except Exception:
            return False, query

    def __run_query_string(self, active, query_string, is_post=False,
                          content_type="application/x-www-form-urlencoded"):
        parsed_query = urlparse.parse_qs(query_string)
        current_subdomain = web.ctx.host.split('.')[0].lower()
        if query_string is None or query_string.strip() == "":
            web_logger.mes()
            return getattr(render, self.sparql_endpoint_title)(
                active=active, 
                sp_title=self.sparql_endpoint_title, 
                sparql_endpoint=self.yasqe_sparql_endpoint, 
                render=render,
                current_subdomain=current_subdomain)
        for k in self.collparam:
            if k in parsed_query:
                query = parsed_query[k][0]
                isupdate = None
                isupdate, sanitizedQuery = self.__is_update_query(query)

                if isupdate != None:
                    if isupdate:
                        raise web.HTTPError(
                            "403 ",
                            {"Content-Type": "text/plain"},
                            "SPARQL Update queries are not permitted."
                        )
                    else:
                        return self.__contact_tp(sanitizedQuery, is_post, content_type)

        raise web.HTTPError(
            "408",
            {"Content-Type": "text/plain"},
            "Not a valid request"
        )

class Main:
    def GET(self):
        web_logger.mes()
        current_subdomain = web.ctx.host.split('.')[0].lower()
        return render.sparql(active="", sp_title="", sparql_endpoint="", current_subdomain=current_subdomain, render=render)

class SparqlIndex(Sparql):
    def __init__(self):
        Sparql.__init__(self, sparql_config["sparql_endpoint_index"],
                       "index", "/index")

class SparqlMeta(Sparql):
    def __init__(self):
        Sparql.__init__(self, sparql_config["sparql_endpoint_meta"],
                       "meta", "/meta")


# Run the application
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='SPARQL OpenCitations web application')
    parser.add_argument(
        '--sync-static',
        action='store_true',
        help='synchronize static files at startup (for local testing or development)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='port to run the application on (default: 8080)'
    )
    
    args = parser.parse_args()
    
    if args.sync_static or sparql_config["sparql_sync_enabled"]:
        # Run sync if either --sync-static is provided (local testing) 
        # or SPARQL_SYNC_ENABLED=true (Docker environment)
        sync_static_files()
    
    # Set the port for web.py
    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", args.port))