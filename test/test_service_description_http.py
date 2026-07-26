# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import shutil
from pathlib import Path

import pytest

import sparql_oc

SERVICE_DESCRIPTIONS = Path("static/service-descriptions")

FIXTURE_FILES = {
    "index.ttl": b"@prefix void: <http://rdfs.org/ns/void#> .\n<urn:index> a void:Dataset .\n",
    "index.jsonld": b'{"@context": {}, "@id": "urn:index"}',
    "index.html": b"<!DOCTYPE html><html><body>index description</body></html>",
    "meta.ttl": b"@prefix void: <http://rdfs.org/ns/void#> .\n<urn:meta> a void:Dataset .\n",
    "void.rdf": (
        b'<?xml version="1.0"?><rdf:RDF '
        b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"></rdf:RDF>'
    ),
}


@pytest.fixture
def service_descriptions():
    SERVICE_DESCRIPTIONS.mkdir(parents=True, exist_ok=True)
    for name, content in FIXTURE_FILES.items():
        (SERVICE_DESCRIPTIONS / name).write_bytes(content)
    yield
    shutil.rmtree(SERVICE_DESCRIPTIONS)


@pytest.mark.parametrize(
    ("path", "accept", "file_name", "content_type"),
    [
        (
            "/index/description",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "index.html",
            "text/html; charset=utf-8",
        ),
        (
            "/index/description",
            "application/ld+json;q=0, text/turtle;q=1",
            "index.ttl",
            "text/turtle; charset=utf-8",
        ),
        (
            "/index/description",
            "text/turtle;q=0.2, application/ld+json;q=1",
            "index.jsonld",
            "application/ld+json; charset=utf-8",
        ),
        (
            "/meta/description",
            "text/turtle",
            "meta.ttl",
            "text/turtle; charset=utf-8",
        ),
        (
            "/.well-known/void",
            "application/rdf+xml",
            "void.rdf",
            "application/rdf+xml; charset=utf-8",
        ),
    ],
)
def test_service_description_negotiates_accept(
    service_descriptions,
    path: str,
    accept: str,
    file_name: str,
    content_type: str,
) -> None:
    response = sparql_oc.app.request(path, headers={"Accept": accept})

    assert response.status == "200 OK"
    assert response.headers == {
        "Content-Type": content_type,
        "Access-Control-Allow-Origin": "*",
        "Vary": "Accept",
    }
    assert response.data == (SERVICE_DESCRIPTIONS / file_name).read_bytes()


def test_service_description_rejects_unavailable_representation(
    service_descriptions,
) -> None:
    response = sparql_oc.app.request(
        "/index/description", headers={"Accept": "application/pdf"}
    )

    assert response.status == "406 Not Acceptable"


@pytest.mark.parametrize(
    ("path", "endpoint_title"),
    [
        ("/index", "index"),
        ("/meta", "meta"),
    ],
)
def test_sparql_endpoint_unchanged_and_links_to_description(
    path: str, endpoint_title: str
) -> None:
    response = sparql_oc.app.request(path)

    assert response.status == "200 OK"
    assert (
        response.headers["Link"]
        == f'</{endpoint_title}/description>; rel="describedby"'
    )
