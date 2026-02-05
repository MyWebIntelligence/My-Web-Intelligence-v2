---
title: 'My Web Intelligence: Enunciation-Level Web Crawling for Authentic Controversy Mapping'
tags:
  - Python
  - digital methods
  - web analysis
  - controversy mapping
  - network analysis
  - NLP
  - computational social science
  - boilerplate removal
  - webometrics
authors:
  - name: Amar Lakel
    orcid: 0000-0001-6062-6257
    affiliation: 1
affiliations:
  - name: MICA Laboratory, Université Bordeaux Montaigne, France
    index: 1
date: 26 January 2026
bibliography: paper.bib
---

# Summary

My Web Intelligence (MWI) is an open-source Python tool that introduces a fundamental methodological shift in digital controversy mapping: extraction at the **enunciation level** rather than the page level. Unlike existing web crawlers that extract all hyperlinks from HTML pages (including navigation, advertisements, widgets, and CMS-generated links), MWI extracts only the links present within the readable content — the actual discourse produced by authors. This distinction operationalizes the difference between technical traces and intentional citation acts, producing authentic cartographies of controversies rather than maps of web infrastructure. MWI further extends this enunciative approach through paragraph-level embeddings and Natural Language Inference, enabling semantic network analysis at the granularity of argumentative units.

# Statement of Need

## A Two-Decade Methodological Gap

MWI addresses a methodological gap identified in webometrics literature over two decades ago. Henzinger, Motwani, and Silverstein [-@henzinger2002challenges] noted that "there has not been much research on link types, and although such research is needed since it may facilitate distinguishing commercial from editorial links or links to metainformation from links that relate to the actual content of the site."

Bar-Ilan [-@barilan2005links] subsequently proposed a multi-faceted framework for hyperlink classification that explicitly included **"link area"** as a key analytical dimension — the position of a hyperlink within page structure (content body, navigation, sidebar, footer). This framework acknowledged that the location of a link carries methodological significance: a link placed within argumentative prose represents a different speech act than a link placed in a navigation menu.

Despite this theoretical recognition, **no social science web crawler has operationalized this distinction**. Tools such as Hyphe [@jacomy2016hyphe], IssueCrawler [@rogers2010issuecrawler], Navicrawler [@jacomy2006navicrawler], and VOSON [@ackland2013voson] extract all hyperlinks present in the HTML source of a page. This includes:

- Navigation links (menus, headers, footers)
- Advertising and affiliate links
- Social media widgets and share buttons
- CMS-generated "related articles" links
- Sidebar and footer links to unrelated content

When researchers use these tools to map controversies, they inadvertently produce **cartographies of web infrastructure** rather than cartographies of discursive exchange. A controversy, in the sociological sense [@venturini2010diving], consists of intentional argumentative acts between enunciators — citations, refutations, endorsements. These acts occur within the body of texts, not in navigation menus.

## MWI's Methodological Innovation

MWI addresses this fundamental gap through what we term **enunciation-level extraction**. The tool first extracts the "readable" content of each page using boilerplate removal algorithms, isolating the actual text produced by the author from the surrounding technical apparatus. Links are then extracted only from this readable content, capturing intentional citation acts rather than technical URL presence.

This approach operationalizes the theoretical framework of "algorithmic hermeneutics" [@lakel2024classification] and "augmented enunciative pragmatics" — treating web data as traces of discursive production requiring interpretation, not self-sufficient network data. The distinction between **enunciative links** (intentional citations within discourse) and **page-level links** (all URLs in HTML) constitutes MWI's core methodological contribution.

The tool has been deployed for controversy analysis of the French "Gilets Jaunes" movement (30,000 pages, 200,000 paragraphs, October 2018 – November 2019), revealing counter-intuitive patterns invisible to page-level analysis: mainstream media informational dominance despite the movement's purportedly "digital native" character.

# Historical Development and Prior Art

MWI's core methodology — extracting hyperlinks only from readable content rather than full HTML — has been implemented since **2014**, as documented in the original prototype funded by the Nouvelle-Aquitaine Regional "Big Data" call for projects. The complete development history is preserved in Software Heritage [@mwi_v1_2016_swh].

The conceptual distinction between "relevant links" (*liens pertinents*) and structural page links was explicitly articulated in the 2014 project presentation [@lakel2015slideshare], which described the platform's goal to "restructure data analyzed by mapping relevant links" (*restructurer les données analysées par la cartographie des liens pertinents*). This formulation demonstrates that the enunciative extraction methodology predates both:

- The mainstream adoption of boilerplate removal tools in web mining (trafilatura [@barbaresi2021trafilatura], 2019)
- Systematic attention to content extraction in digital methods literature

The methodology was first publicly presented at DHNord 2016 [@lakel2016dhnord] alongside a comparative workshop with Hyphe, establishing MWI as a methodological alternative to page-level extraction tools. The article in *Les Cahiers du numérique* [@lakel2017analyse] explicitly noted: "For total page link extraction, refer to Hyphe software" (*Pour l'extraction total des liens de la page se reporter au Logiciel Hyphe*) — demonstrating conscious methodological differentiation.

| Date | Milestone | Documentation |
|------|-----------|---------------|
| 2014 | Regional funding, prototype development | SlideShare presentation [@lakel2015slideshare] |
| 2015 | Public presentation CHU Bordeaux | SlideShare (5,000+ views) |
| 2016 | DHNord conference + workshop | HAL hal-03351672 [@lakel2016dhnord] |
| 2016 | Code archived | Software Heritage [@mwi_v1_2016_swh] |
| 2017 | Methodological publication | *Les Cahiers du numérique* [@lakel2017analyse] |
| 2021 | Software paper (French) | *I2D* [@lakel2021mwi] |
| 2026 | MWI v2 with embeddings/NLI | This paper, Zenodo [@mwi2026] |

# Functionality

## Enunciation-Level Corpus Constitution (Core Innovation)

- **Readable content extraction**: Boilerplate removal isolates author-produced text from page infrastructure (navigation, ads, widgets, CMS elements)
- **Enunciative link extraction**: Hyperlinks extracted exclusively from readable content, capturing intentional citations rather than technical URL presence
- **Focus crawling on discourse**: Depth crawling follows only enunciative links, building corpora of discursive exchange rather than web topology
- **Search engine bootstrapping**: Corpus seeding via SerpAPI (Google, Bing, DuckDuckGo) with temporal filtering
- **Relevance qualification**: Lemma-based scoring with optional LLM validation (OpenRouter) operating on readable content only

## Paragraph-Level Semantic Analysis

- **Paragraph extraction**: Readable content segmented into discrete enunciative units
- **Embeddings generation**: Multi-provider vectorization (OpenAI, Mistral, Gemini, HuggingFace, Ollama) at paragraph granularity
- **Semantic similarity**: Three scalable methods (exact cosine, LSH approximate, FAISS ANN)
- **Natural Language Inference**: Cross-encoder classification (mDeBERTa XNLI multilingual) producing entailment/neutral/contradiction relations between paragraph pairs
- **Pseudolinks**: Semantic connections between paragraphs across documents, extending enunciative analysis beyond explicit citation to implicit argumentative relations

## Network Export and Reproducibility

- **Multi-level aggregation**: Paragraph pairs, expression (page), and domain-level projections
- **Export formats**: CSV, GEXF (Gephi-compatible), raw corpus with full audit trail
- **Docker infrastructure**: One-command reproducible deployment
- **Database migrations**: Schema versioning for longitudinal studies

# State of the Field

MWI is, to our knowledge, the **first and only robust open-source web crawling tool** that distinguishes enunciative links from page-level links for social science research:

| Tool | Extraction Level | Link Source | Methodological Basis |
|------|-----------------|-------------|---------------------|
| Hyphe [@jacomy2016hyphe] | Page HTML | All page links | Web entity curation |
| IssueCrawler [@rogers2010issuecrawler] | Page HTML | All page links | Co-link analysis |
| Navicrawler [@jacomy2006navicrawler] | Page HTML | All page links | Manual navigation |
| VOSON [@ackland2013voson] | Page HTML | All page links | Hyperlink networks |
| **MWI** | **Readable content** | **Enunciative links only** | **Discursive exchange** |

This distinction has significant implications for controversy studies. Existing tools produce networks where nodes (pages/domains) are connected by edges that mix intentional citations with navigational artifacts. MWI produces networks where edges represent exclusively the citation acts performed by authors within their discourse — the actual fabric of controversies.

The distinction operationalizes Bar-Ilan's [-@barilan2005links] theoretical framework, which identified "link area" as a key classification dimension but noted that operational tools had not yet implemented this distinction. MWI fills this gap, providing researchers with the first tool capable of building networks based on discursive intentionality rather than technical HTML structure.

The paragraph-level pseudolinks feature extends this approach, detecting semantic relations (entailment, contradiction, neutrality) between argumentative units across the corpus, enabling cartography of implicit argumentative structures beyond explicit hyperlink citation.

# Research Applications

- **Health information ecosystem mapping**: enunciative networks of medical authority [@lakel2020positions; @lakel2022health]
- **Digital humanities community**: citation practices vs. institutional linking [@lakel2016dhnord; @lakel2017analyse]
- **Gilets Jaunes controversy**: mainstream media hegemony revealed through enunciative analysis (30,000 pages, 200,000 paragraphs)
- **Intellectual influence networks**: discourse-level rather than page-level citation [@cormerais2023branco]
- **Automatic classification of digital corpora**: interdisciplinary problematization [@lakel2024classification]
- **Communication sciences methodology**: digital methods epistemology [@cormerais2016sic; @cormerais2018recherches]

# Acknowledgements

MWI development was supported by the MICA Laboratory at Université Bordeaux Montaigne and the Nouvelle-Aquitaine Region (2014 "Big Data" call for projects). The author thanks Franck Cormerais, Olivier Le Deuff, Nathalie Pinede and the E3D research group for theoretical discussions on enunciative pragmatics, David Bruant for foundational software development (2014-2016), and Jean Devalance for contributions to MWI python version.

# References
