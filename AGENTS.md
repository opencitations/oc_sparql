<!--
SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>

SPDX-License-Identifier: CC-BY-4.0
-->

# QLever query cookbook

Tested on QLever [0.6.0](https://github.com/ad-freiburg/qlever/releases/tag/v0.6.0).

## Slow queries

### `OPTIONAL` ignores the bindings around it

QLever runs the `OPTIONAL` over the whole dataset and joins the result with the rest only at the end, so the fix is to repeat the binding inside the group.

Don't:

```sparql
PREFIX br: <https://w3id.org/oc/meta/br/>
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
SELECT ?br ?scheme ?value WHERE {
  VALUES ?br { br:0612058700 }
  OPTIONAL {
    ?br datacite:hasIdentifier ?id .
    ?id datacite:usesIdentifierScheme ?scheme ;
        literal:hasLiteralValue ?value
  }
}
```

Do:

```sparql
PREFIX br: <https://w3id.org/oc/meta/br/>
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
SELECT ?br ?scheme ?value WHERE {
  VALUES ?br { br:0612058700 }
  OPTIONAL {
    VALUES ?br { br:0612058700 }  # the same binding, repeated inside the group
    ?br datacite:hasIdentifier ?id .
    ?id datacite:usesIdentifierScheme ?scheme ;
        literal:hasLiteralValue ?value
  }
}
```

Issue: [#2429](https://github.com/ad-freiburg/qlever/issues/2429).

### Pairs in `VALUES`

A `VALUES` can list pairs of values, such as the scheme and the value of an identifier, which belong together. With pairs, QLever reads every triple of a property before it looks for the few pairs in the list. To fix it, keep the pairs and add a second `VALUES` with only one of the two columns.

Don't:

```sparql
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
SELECT ?br ?scheme ?value WHERE {
  VALUES (?scheme ?value) {
    (datacite:doi "10.1007/978-1-4020-9632-7")
    (datacite:openalex "W4410092270")
  }
  ?id datacite:usesIdentifierScheme ?scheme ;
      literal:hasLiteralValue ?value .
  ?br datacite:hasIdentifier ?id
}
```

Do:

```sparql
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
SELECT ?br ?scheme ?value WHERE {
  VALUES (?scheme ?value) {
    (datacite:doi "10.1007/978-1-4020-9632-7")
    (datacite:openalex "W4410092270")
  }
  VALUES ?value { "10.1007/978-1-4020-9632-7" "W4410092270" }  # the same values again, without the scheme
  ?id datacite:usesIdentifierScheme ?scheme ;
      literal:hasLiteralValue ?value .
  ?br datacite:hasIdentifier ?id
}
```

Issue: [#2423](https://github.com/ad-freiburg/qlever/issues/2423).

## Wrong results

### `FILTER` inside `OPTIONAL` on an outer variable

A `FILTER` inside an `OPTIONAL` may compare a value found in the group with a variable bound outside it. QLever evaluates the group on its own, before it joins it with the rest, so the filter sees the outer variable as unbound. The `OPTIONAL` then adds nothing, and no error is raised. To fix it, leave the filter out of the group and make the comparison after it, where both variables are bound.

Don't:

```sparql
PREFIX br: <https://w3id.org/oc/meta/br/>
PREFIX frbr: <http://purl.org/vocab/frbr/core#>
PREFIX prism: <http://prismstandard.org/namespaces/basic/2.0/>
SELECT ?br ?date ?cdate WHERE {
  VALUES ?br { br:06601010991 }
  ?br prism:publicationDate ?date ;
      frbr:partOf ?container .
  OPTIONAL {
    ?container prism:publicationDate ?cdate
    FILTER(?cdate = ?date)
  }
}
```

Do:

```sparql
PREFIX br: <https://w3id.org/oc/meta/br/>
PREFIX frbr: <http://purl.org/vocab/frbr/core#>
PREFIX prism: <http://prismstandard.org/namespaces/basic/2.0/>
SELECT ?br ?date ?cdate WHERE {
  VALUES ?br { br:06601010991 }
  ?br prism:publicationDate ?date ;
      frbr:partOf ?container .
  OPTIONAL { ?container prism:publicationDate ?any }
  BIND(IF(?any = ?date, ?any, ?none) AS ?cdate)  # the comparison, after the group
}
```

Issue: [#2509](https://github.com/ad-freiburg/qlever/issues/2509).