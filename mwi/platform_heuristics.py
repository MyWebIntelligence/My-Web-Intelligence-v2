"""Per-platform domain-resolution heuristics (sprint-heuristique).

PLATFORM_HEURISTICS maps a host suffix to a resolution rule:

    {host: {"url": <python regex str | None>, "html": <signal>}}

- "url": a regex with ONE capturing group extracting the logical editorial
  entity from the URL (e.g. a channel/handle/subreddit), matched on a label
  boundary; None when the entity is not reliably in the URL path.
- "html": one declarative signal used by `heuristic update --html` to recover a
  better editorial URL from the page HTML, then re-resolved through the URL rule.
  One of: ldjson_author, ldjson_publisher, canonical, og_url, rel_author,
  dc_creator, citation_author.

Only hosts listed here are ever re-grouped by `heuristic update`; every other
host keeps its bare netloc as its domain. Override the whole table via
`settings.platform_heuristics` (same shape); leave it undefined to use this
default. This table subsumes the legacy flat `settings.heuristics` (URL regexes
merged in verbatim) and fixes the YouTube channel/c/user over-capture.
"""

PLATFORM_HEURISTICS = {
    '500px.com': {"url": None, "html": 'ldjson_author'},
    'academia.edu': {"url": r"([a-z0-9\-_]*\.?academia\.edu/(?!(?:search)|(?:Documents)|(?:login)|(?:signup)|(?:about)|(?:hiring))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'agoravox.fr': {"url": r"(agoravox\.fr/auteur/[\w%-]+)", "html": 'ldjson_author'},
    'agoravox.tv': {"url": r"(agoravox\.tv/auteur/[\w%-]+)", "html": 'ldjson_author'},
    'amazon.fr': {"url": None, "html": 'canonical'},
    'ameblo.jp': {"url": r"(ameblo\.jp/(?!(?:search)|(?:hashtag)|(?:login))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'anchor.fm': {"url": r"(anchor\.fm/(?!(?:switch)|(?:dashboard))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'answers.com': {"url": None, "html": 'ldjson_publisher'},
    'artstation.com': {"url": r"(artstation\.com/(?!(?:artwork|search|marketplace|jobs|blogs|learning|prints|channels|contests|guides|podcast|about|terms|privacy)(?:[/.?]|$))[a-zA-Z0-9%_-]+)", "html": 'ldjson_author'},  # noqa: E501
    'ask.com': {"url": None, "html": 'ldjson_publisher'},
    'bandcamp.com': {"url": None, "html": None},
    'behance.net': {"url": r"(behance\.net/(?!(?:gallery|galleries|search|assets|joblist|for_you|live|blog|hire|jobs|collection|discover|about)(?:[/.?]|$))[a-zA-Z0-9%_-]+)", "html": 'ldjson_author'},  # noqa: E501
    'bilibili.com': {"url": None, "html": 'ldjson_author'},
    'bitbucket.org': {"url": r"(bitbucket\.org/(?!(?:product)|(?:account)|(?:dashboard)|(?:search))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'bitchute.com': {"url": r"(bitchute\.com/channel/[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'blog4ever.com': {"url": None, "html": None},
    'blogs.mediapart.fr': {"url": r"blogs\.mediapart\.fr/(?:blog/)?(?!(?:edition|sitemap)(?:[/.?]|$))([a-zA-Z0-9%._-]+)", "html": 'rel_author', "prefix": 'blogs.mediapart.fr/'},  # noqa: E501
    'blogspot.com': {"url": None, "html": None},
    'bondyblog.fr': {"url": None, "html": 'ldjson_author'},
    'brighteon.com': {"url": r"(brighteon\.com/channels/[a-zA-Z0-9%_-]+)", "html": 'ldjson_author'},  # noqa: E501
    'bsky.app': {"url": r"([a-z0-9\-_]*\.?bsky\.app/profile/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'calameo.com': {"url": None, "html": 'ldjson_author'},
    'canalblog.com': {"url": None, "html": None},
    'change.org': {"url": r"(change\.org/p/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},
    'dailymotion.com': {"url": r"([a-z0-9\-_]+\.dailymotion\.com/(?!(?:video)|(?:search)|(?:topic)|(?:explore)|(?:pageitem)(?:[/?]|$)|(?:embed)(?:[/?]|$)|(?:player)(?:[/?]|$))[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'dailymotion_channel'},  # noqa: E501
    'dev.to': {"url": r"(dev\.to/(?!(?:search)|(?:tags)|(?:top)|(?:latest)|(?:enter)|(?:about)|(?:contact)|(?:privacy)|(?:terms)|(?:t/)|(?:pod)|(?:videos))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'deviantart.com': {"url": r"(deviantart\.com/(?!(?:users|search|tag|topic|daily-deviations|shop|forum|groups|join|settings|notifications|watch|about|core-membership|print|developers|team)(?:[/.?]|$))[a-zA-Z0-9%_-]+)", "html": 'ldjson_author'},  # noqa: E501
    'diigo.com': {"url": r"(diigo\.com/user/[a-zA-Z0-9%_.-]+)", "html": 'canonical'},
    'docdroid.net': {"url": None, "html": 'ldjson_publisher'},
    'dribbble.com': {"url": r"(dribbble\.com/(?!(?:shots|search|designers|jobs|tags|about|stories|resources|teams|colors|following|signup|session|pro|integrations|shop|blog|pricing)(?:[/.?]|$))[a-zA-Z0-9%_-]+)", "html": 'ldjson_author'},  # noqa: E501
    'e-monsite.com': {"url": None, "html": None},
    'ehow.com': {"url": None, "html": 'ldjson_publisher'},
    'eklablog.com': {"url": None, "html": None},
    'eklablog.fr': {"url": None, "html": None},
    'etsy.com': {"url": r"(etsy\.com/(?:shop|people)/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},
    'eventbrite.com': {"url": r"(eventbrite\.com/o/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},
    'eventbrite.fr': {"url": r"(eventbrite\.fr/o/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},
    'ezinearticles.com': {"url": None, "html": 'ldjson_author'},
    'facebook.com': {"url": r"([a-z0-9\-_]+\.facebook\.com/(?:groups/[a-zA-Z0-9%\.\-_]+|pages/[a-zA-Z0-9%\.\-_]+/[0-9]+|(?!(?:notes)|(?:share)|(?:sharer)|(?:login)|(?:help)|(?:watch)|(?:events)|(?:groups)|(?:marketplace)|(?:gaming)|(?:stories)|(?:reel)|(?:wui)|(?:[a-zA-Z0-9%_\-]+\.php)(?:[/?]|$)|(?:dialog)(?:[/?]|$)|(?:plugins)(?:[/?]|$)|(?:pages)(?:[/?]|$))[a-zA-Z0-9%\.\-_]+))/?\??", "html": 'og_url', "alias": 'facebook.com', "lower": True},  # noqa: E501
    'fandom.com': {"url": r"([a-z0-9\-_]+\.fandom\.com)", "html": 'canonical'},
    'fb.com': {"url": None, "html": 'og_url'},
    'feedly.com': {"url": None, "html": 'canonical'},
    'fextralife.com': {"url": None, "html": None},
    'figshare.com': {"url": None, "html": 'dc_creator'},
    'flickr.com': {"url": r"(flickr\.com/photos/(?!(?:tags|search|groups|explore|map|favorites)(?:[/.?]|$))[a-zA-Z0-9%\.\-_@]+)", "html": 'canonical'},  # noqa: E501
    'flipboard.com': {"url": r"(flipboard\.com/@[\w%.-]+)", "html": 'canonical'},
    'forumactif.com': {"url": None, "html": None},
    'forumactif.org': {"url": None, "html": None},
    'fr.calameo.com': {"url": None, "html": 'ldjson_author'},
    'fr.quora.com': {"url": None, "html": 'canonical'},
    'fr.slideshare.net': {"url": None, "html": 'ldjson_author'},
    'fr.wikihow.com': {"url": None, "html": 'ldjson_publisher'},
    'gamepedia.com': {"url": None, "html": None},
    'getpocket.com': {"url": None, "html": 'canonical'},
    'ghost.io': {"url": None, "html": None},
    'github.com': {"url": r"(github\.com/(?!(?:search)|(?:explore)|(?:trending)|(?:login)|(?:join)|(?:settings)|(?:notifications)|(?:marketplace)|(?:sponsors)|(?:features)|(?:pricing)|(?:about)|(?:topics)|(?:collections)|(?:events)|(?:orgs))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'gitlab.com': {"url": r"(gitlab\.com/(?!(?:explore)|(?:search)|(?:help)|(?:users/sign_in)|(?:dashboard))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'gofundme.com': {"url": r"(gofundme\.com/f/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},
    'gumroad.com': {"url": None, "html": None},
    'hardware.fr': {"url": None, "html": 'canonical'},
    'hautetfort.com': {"url": None, "html": None},
    'hubpages.com': {"url": r"(hubpages\.com/@[^/?#]+)", "html": 'ldjson_author'},
    'imgur.com': {"url": None, "html": 'ldjson_author'},
    'instagram.com': {"url": r"([a-z0-9\-_]+\.instagram\.com/(?!(?:explore)|(?:accounts)|(?:about)|(?:legal)|(?:developer)|(?:p/)|(?:reel/)|(?:stories/))[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'ldjson_author', "alias": 'instagram.com', "lower": True},  # noqa: E501
    'instructables.com': {"url": r"(instructables\.com/member/[^/?#]+)", "html": 'ldjson_author'},
    'issuu.com': {"url": r"(issuu\.com/(?!(?:search|explore|signin|signup|login|publish|features|pricing|about|home|stores|call-for-content|legal|careers|press|plans|help|blog|oembed)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'jimdo.com': {"url": None, "html": None},
    'jimdofree.com': {"url": None, "html": None},
    'ko-fi.com': {"url": r"(ko-fi\.com/(?!(?:explore)|(?:about)|(?:gold)|(?:manage))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'leboncoin.fr': {"url": None, "html": 'canonical'},
    'linkedin.com': {"url": r"([a-z0-9\-_]+\.linkedin\.com/(?:in|company)/[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'ldjson_author'},  # noqa: E501
    'linktr.ee': {"url": r"(linktr\.ee/(?!(?:admin)|(?:s/))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'list.ly': {"url": None, "html": 'canonical'},
    'livejournal.com': {"url": None, "html": None},
    'medium.com': {"url": r"([a-z0-9\-_]*\.?medium\.com/(?!(?:search)|(?:explore)|(?:topics)|(?:me/)|(?:plans)|(?:about)|(?:creators)|(?:tag/)|(?:membership)|(?:p/))[a-zA-Z0-9%@\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'meetup.com': {"url": r"(meetup\.com/(?!(?:find)|(?:topics)|(?:cities)|(?:login)|(?:register)|(?:about)|(?:help))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'mesopinions.com': {"url": None, "html": 'canonical'},
    'miraheze.org': {"url": None, "html": None},
    'mixcloud.com': {"url": r"(mixcloud\.com/(?!(?:discover|search|upload|live|categories|browse|settings|about|help|jobs|tag|popular|new|terms|privacy|select)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'netvibes.com': {"url": r"(netvibes\.com/(?!(?:en|fr|de|es|it|pt|ru|ja|zh|nl|privacypolicy|subscribe|tour|api|apps|basic|download|signin|signup)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'news.google.com': {"url": None, "html": 'canonical'},
    'note.com': {"url": r"(note\.com/(?!(?:search)|(?:explore)|(?:ranking)|(?:topics)|(?:hashtag)|(?:login)|(?:signup))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'odysee.com': {"url": r"(odysee\.com/@[a-zA-Z0-9%\.\-_:]+)", "html": 'canonical'},
    'ok.ru': {"url": None, "html": 'og_url'},
    'open.spotify.com': {"url": r"(open\.spotify\.com/(?:show|artist)/[a-zA-Z0-9%]+)", "html": 'canonical'},  # noqa: E501
    'over-blog.com': {"url": None, "html": None},
    'padlet.com': {"url": r"(padlet\.com/(?!(?:dashboard|gallery|auth|login|signup|about|features|pricing|search|home|my|settings|help|blog|apps|join|browse|tags|explore)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'pagesperso-orange.fr': {"url": r"(pagesperso-orange\.fr/~[\w%.-]+)", "html": 'canonical'},
    'paper.li': {"url": r"(paper\.li/(?!(?:edition|tag|topic|search|about|faq|pricing|login|signup|home)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'patreon.com': {"url": r"(patreon\.com/(?!(?:search)|(?:explore)|(?:login)|(?:signup)|(?:about)|(?:policy)|(?:careers)|(?:c/))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'pearltrees.com': {"url": r"(pearltrees\.com/(?!(?:about|faq|help|pricing|business|education|download|login|signup|search|s)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'pinterest.com': {"url": r"([a-z0-9\-_]+\.pinterest\.com/(?!(?:pin)|(?:search)|(?:ideas)|(?:today)|(?:business))[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'og_url'},  # noqa: E501
    'pinterest.fr': {"url": r"([a-z0-9\-_]+\.pinterest\.fr/(?!(?:pin)|(?:search)|(?:ideas))[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'og_url'},  # noqa: E501
    'prezi.com': {"url": None, "html": 'ldjson_author'},
    'proboards.com': {"url": None, "html": None},
    'quora.com': {"url": None, "html": 'canonical'},
    'reddit.com': {"url": r"([a-z0-9\-_]*\.?reddit\.com/r/(?!(?:all)|(?:popular)|(?:home))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'researchgate.net': {"url": r"(researchgate\.net/profile/[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'rumble.com': {"url": r"(rumble\.com/(?:c|user)/[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},
    'scoop.it': {"url": r"(scoop\.it/u/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},
    'scribd.com': {"url": None, "html": 'ldjson_author'},
    'senscritique.com': {"url": None, "html": 'canonical'},
    'skyrock.com': {"url": None, "html": None},
    'slideshare.net': {"url": r"([a-z0-9\-_]+\.slideshare\.net/(?!(?:search)|(?:explore)|(?:featured))[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'ldjson_author'},  # noqa: E501
    'snapchat.com': {"url": r"([a-z0-9\-_]*\.?snapchat\.com/add/[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'soundcloud.com': {"url": r"(soundcloud\.com/(?!(?:search)|(?:discover)|(?:stream)|(?:upload)|(?:you/)|(?:charts)|(?:tags/)|(?:stations)|(?:login)|(?:pages))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'speakerdeck.com': {"url": r"(speakerdeck\.com/(?!(?:p|explore|search|about|terms|privacy|signin|signup|features|pricing|help|oembed|category)(?:[/.?]|$))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'squarespace.com': {"url": None, "html": None},
    'ssrn.com': {"url": None, "html": 'citation_author'},
    'stackexchange.com': {"url": None, "html": 'canonical'},
    'stackoverflow.com': {"url": None, "html": 'canonical'},
    'substack.com': {"url": None, "html": None},
    't.me': {"url": r"(t\.me/(?!(?:addstickers)|(?:joinchat)|(?:addtheme)|(?:share)|(?:login)|(?:auth)|(?:dl))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'telegram.me': {"url": r"(telegram\.me/(?!(?:addstickers)|(?:joinchat)|(?:share))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical'},  # noqa: E501
    'threads.net': {"url": r"([a-z0-9\-_]*\.?threads\.net/@[a-zA-Z0-9%\.\-_]+)", "html": 'canonical', "alias": 'threads.net', "lower": True},  # noqa: E501
    'tiktok.com': {"url": r"([a-z0-9\-_]*\.?tiktok\.com/@[a-zA-Z0-9%\.\-_]+)", "html": 'canonical', "alias": 'tiktok.com', "lower": True},  # noqa: E501
    'trello.com': {"url": None, "html": 'canonical'},
    'tripadvisor.fr': {"url": None, "html": 'canonical'},
    'trustpilot.com': {"url": r"trustpilot\.com/review/([\w%.-]+)", "html": 'canonical'},
    'tumblr.com': {"url": None, "html": None},
    'twitch.tv': {"url": r"([a-z0-9\-_]*\.?twitch\.tv/(?!(?:directory)|(?:search)|(?:downloads)|(?:jobs)|(?:turbo)|(?:settings)|(?:subscriptions)|(?:p/))[a-zA-Z0-9%\.\-_]+)", "html": 'ldjson_author'},  # noqa: E501
    'twitter.com': {"url": r"([a-z0-9\-_]*\.?twitter\.com/(?!(?:hashtag)|(?:search)|(?:home)|(?:share)|(?:explore)|(?:login)|(?:i/)|(?:settings)|(?:notifications)|(?:messages)|(?:compose)|(?:tos)|(?:privacy)|(?:intent)|(?:web))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical', "alias": 'x.com', "lower": True},  # noqa: E501
    'typepad.com': {"url": None, "html": None},
    'vimeo.com': {"url": r"([a-z0-9\-_]+\.vimeo\.com/(?!(?:search)|(?:categories)|(?:watch)|(?:features)|(?:about))[a-zA-Z0-9%\.\-_]+)/?\??", "html": 'og_url'},  # noqa: E501
    'vk.com': {"url": r"(vk\.com/(?!(?:feed)|(?:im)|(?:friends)|(?:search)|(?:login)|(?:join)|(?:about)|(?:away\.php)|(?:share\.php))[a-zA-Z0-9%\.\-_]+)", "html": 'og_url'},  # noqa: E501
    'wakelet.com': {"url": None, "html": 'canonical'},
    'wattpad.com': {"url": None, "html": 'ldjson_author'},
    'webnode.fr': {"url": None, "html": None},
    'weebly.com': {"url": None, "html": None},
    'weibo.com': {"url": None, "html": 'canonical'},
    'wikia.com': {"url": None, "html": None},
    'wikibooks.org': {"url": None, "html": 'canonical'},
    'wikidot.com': {"url": None, "html": None},
    'wikihow.com': {"url": None, "html": 'ldjson_publisher'},
    'wikiversity.org': {"url": None, "html": 'canonical'},
    'wixsite.com': {"url": None, "html": None},
    'wordpress.com': {"url": None, "html": None},
    'x.com': {"url": r"([a-z0-9\-_]*\.?x\.com/(?!(?:hashtag)|(?:search)|(?:home)|(?:share)|(?:explore)|(?:login)|(?:i/)|(?:settings)|(?:notifications)|(?:messages)|(?:compose)|(?:tos)|(?:privacy)|(?:intent)|(?:web))[a-zA-Z0-9%\.\-_]+)", "html": 'canonical', "alias": 'x.com', "lower": True},  # noqa: E501
    'xooit.com': {"url": None, "html": None},
    'xooit.org': {"url": None, "html": None},
    'yelp.fr': {"url": r"yelp\.fr/biz/([\w%-]+)", "html": 'canonical'},
    'youtu.be': {"url": None, "html": 'ldjson_author'},
    'youtube.com': {"url": r"([a-z0-9\-_]*\.?youtube\.com/(?:@[a-zA-Z0-9%\.\-_]+|(?:channel|c|user)/[a-zA-Z0-9%\.\-_]+))", "html": 'itemprop_author'},  # noqa: E501
    'zenodo.org': {"url": None, "html": 'ldjson_author'},
}
