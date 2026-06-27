"""
Command Line Interface
"""
import argparse
from typing import Any
from .controller import (
    DbController,
    DomainController,
    LandController,
    HeuristicController,
    TagController,
    EmbeddingController,
    SearchController,
)
from .serpapi_router import SearchRouter as SerpApiRouter


def command_run(args: Any):
    """Execute a command from arguments provided as dict or namespace.

    Converts dictionary arguments to argparse.Namespace if needed, then
    dispatches the command to the appropriate controller.

    Args:
        args: Command arguments as either a dictionary or argparse.Namespace
            object. If dict, it will be converted to Namespace.

    Returns:
        None. The function delegates to dispatch() which calls the
        appropriate controller method.

    Notes:
        This is the programmatic entry point for running commands without
        parsing command-line arguments. Useful for testing and embedding
        MyWI in other Python applications.
    """
    if isinstance(args, dict):
        args = argparse.Namespace(**args)
    dispatch(args)


def command_input():
    """Parse command-line arguments and execute the corresponding command.

    Creates an ArgumentParser with all MyWebIntelligence command-line options,
    parses sys.argv, processes language arguments, and dispatches to the
    appropriate controller.

    Returns:
        None. The function delegates to dispatch() which calls the
        appropriate controller method.

    Notes:
        This is the main entry point for command-line usage. It supports
        nested commands (object, verb, optional subverb) and a wide range
        of options including land management, crawling, export, LLM
        validation, and embedding operations.

        Language arguments are automatically converted from comma-separated
        strings to lists for multi-language support.
    """
    parser = argparse.ArgumentParser(description='MyWebIntelligence Command Line Project Manager.')
    parser.add_argument('object',
                        metavar='object',
                        type=str,
                        help='Object to interact with [db, land, request]')
    parser.add_argument('verb',
                        metavar='verb',
                        type=str,
                        help='Verb depending on target object')
    # Optional sub-verb (e.g., `land llm validate`)
    parser.add_argument('subverb',
                        metavar='subverb',
                        type=str,
                        nargs='?',
                        help='Optional sub-verb for nested commands')
    parser.add_argument('--land',
                        type=str,
                        help='Name of the land to work with')
    parser.add_argument('--name',
                        type=str,
                        help='Name of the object')
    parser.add_argument('--desc',
                        type=str,
                        help='Description of the object')
    parser.add_argument('--type',
                        type=str,
                        help='Export type, see README for reference')
    parser.add_argument('--terms',
                        type=str,
                        help='Terms to add to request dictionnary, comma separated')
    parser.add_argument('--urls',
                        type=str,
                        help='URL to add to request, comma separated',
                        nargs='?')
    parser.add_argument('--path',
                        type=str,
                        help='Path to local file containing URLs',
                        nargs='?')
    parser.add_argument('--limit',
                        type=int,
                        help='Set limit of URLs to crawl',
                        nargs='?',
                        const=0)
    parser.add_argument('--minrel',
                        type=int,
                        help='Set minimum relevance threshold',
                        nargs='?',
                        const=0)
    parser.add_argument('--maxrel',
                        type=int,
                        help='Set maximum relevance threshold',
                        nargs='?',
                        const=0)
    parser.add_argument('--vacuum',
                        action='store_true',
                        default=False,
                        help='Run VACUUM after deletion to reclaim disk space (slow on large databases)')
    parser.add_argument('--http',
                        type=str,
                        help='Limit crawling to specific http status (re crawling)',
                        nargs='?')
    parser.add_argument('--retry-status',
                        type=str,
                        dest='retry_status',
                        help='Comma-separated HTTP status codes to retry, ignoring fetched_at. '
                             'Example: "403,429,406". Useful to backfill the cascade '
                             'fallback (sprint-403) on previously crawled URLs.',
                        default=None,
                        nargs='?')
    parser.add_argument('--depth',
                        type=int,
                        help='Only crawl URLs with the specified depth (for land crawl)',
                        nargs='?')
    parser.add_argument('--fullhtml',
                        type=str,
                        help='Store raw HTML in database (TRUE/FALSE). '
                             'For land create: sets the default. '
                             'For land crawl: overrides land default if specified.',
                        nargs='?',
                        const='TRUE',
                        default=None)
    parser.add_argument('--lang',
                        type=str,
                        help='Language(s) of the project, comma-separated '
                             '(default: fr for land create; the land\'s '
                             'primary language for land urlist).',
                        default=None,
                        nargs='?')
    parser.add_argument('--merge',
                        type=str,
                        help='Merge strategy for readable: smart_merge, mercury_priority, preserve_existing',
                        default='smart_merge',
                        nargs='?')
    parser.add_argument('--llm',
                        type=str,
                        help='Toggle OpenRouter validation during readable pipeline (true|false, default=false)',
                        default='false')
    parser.add_argument('--query',
                        type=str,
                        help='Search query to fetch URLs from SerpAPI',
                        nargs='?')
    engine_choices = sorted(SerpApiRouter.engines())
    parser.add_argument('--engine',
                        type=str,
                        help='Search engine for urlist (' + '|'.join(engine_choices) + ')',
                        default='google',
                        choices=engine_choices,
                        nargs='?')
    parser.add_argument('--gl',
                        type=str,
                        help='Optional country restriction for SerpAPI Google urlist '
                             '(ISO 3166 code, e.g. us, fr). Default: none — searches '
                             'are scoped by language only (hl/lr)',
                        default=None,
                        nargs='?')
    parser.add_argument('--datestart',
                        type=str,
                        help='Start date (YYYY-MM-DD) for SerpAPI urlist filtering',
                        nargs='?')
    parser.add_argument('--dateend',
                        type=str,
                        help='End date (YYYY-MM-DD) for SerpAPI urlist filtering',
                        nargs='?')
    parser.add_argument('--timestep',
                        type=str,
                        help='Date window size when iterating between datestart/dateend (day|week|month)',
                        default='week',
                        nargs='?')
    parser.add_argument('--progress',
                        action='store_true',
                        help='Display SerpAPI progress per date window')
    parser.add_argument('--sleep',
                        type=float,
                        help='Base delay (seconds) between SerpAPI calls to avoid rate limits',
                        default=1.0,
                        nargs='?')
    parser.add_argument('--threshold',
                        type=float,
                        help='Similarity threshold for embeddings',
                        nargs='?')
    parser.add_argument('--method',
                        type=str,
                        help='Similarity method (default: cosine)',
                        nargs='?')
    parser.add_argument('--backend',
                        type=str,
                        help='Similarity backend for ANN (bruteforce|faiss)',
                        nargs='?')
    parser.add_argument('--topk',
                        type=int,
                        help='Keep at most top-K neighbors per paragraph',
                        nargs='?')
    parser.add_argument('--lshbits',
                        type=int,
                        help='Number of LSH hyperplanes/bits (for cosine_lsh method)',
                        nargs='?')
    parser.add_argument('--maxpairs',
                        type=int,
                        help='Max number of similarity pairs to insert (cap)',
                        nargs='?')
    parser.add_argument('--force',
                        action='store_true',
                        help='Force: re-validate previous "non" verdicts (land llm validate), '
                             'refresh existing data (land seorank), '
                             'skip confirmation (embedding reset)')
    parser.add_argument('--issuecrawl',
                        action='store_true',
                        help='LLM gate: stricter "controversy analysis" prompt — keep only '
                             'editorial/position-taking pages on the project issue; drop '
                             'index/navigation and generic company-presentation pages. '
                             'Overrides settings.openrouter_issue_mode for this run '
                             '(land crawl | readable | consolidate | llm validate)')
    # Media maintenance verbs (land media_stats / preview_deletion / reanalyze)
    parser.add_argument('--minwidth',
                        type=int,
                        help='Minimum media width in pixels (default: settings.media_min_width)',
                        nargs='?')
    parser.add_argument('--minheight',
                        type=int,
                        help='Minimum media height in pixels (default: settings.media_min_height)',
                        nargs='?')
    parser.add_argument('--maxsize',
                        type=float,
                        help='Maximum media file size in MB (default: settings.media_max_file_size)',
                        nargs='?')
    parser.add_argument('--suppress',
                        action='store_true',
                        help='For land reanalyze: delete non-conforming media after confirmation')
    parser.add_argument('--dryrun',
                        action='store_true',
                        help='Dry run mode - show what would be changed without modifying database')
    # land normalize options
    parser.add_argument('--dry-run',
                        type=str,
                        dest='dry_run',
                        help='For land normalize: TRUE to preview, FALSE/absent to apply.',
                        nargs='?',
                        const='TRUE',
                        default=None)
    parser.add_argument('--reset-status',
                        type=str,
                        dest='reset_status',
                        help='For land normalize: TRUE to clear http_status / fetched_at on renamed expressions.',
                        nargs='?',
                        const='TRUE',
                        default=None)
    parser.add_argument('--verbose',
                        type=str,
                        help='For land normalize: TRUE to print one line per change.',
                        nargs='?',
                        const='TRUE',
                        default=None)
    parser.add_argument('--db',
                        type=str,
                        help='Override the SQLite database path. Accepts any filename '
                             '(no need to be named mwi.db). Useful to operate on parallel '
                             'databases without setting MYWI_DATA_DIR.',
                        default=None)
    # Multi-API search router (search run|list|usage|check)
    parser.add_argument('--strategy',
                        type=str,
                        choices=['fallback', 'parallel'],
                        help='Orchestration strategy for `search run` '
                             '(fallback preserves quotas, parallel triangulates).',
                        default=None,
                        nargs='?')
    parser.add_argument('--language',
                        type=str,
                        help='Language code for `search run` (e.g. fr, en). '
                             'Default: the land\'s primary language.',
                        default=None,
                        nargs='?')
    parser.add_argument('--providers',
                        type=str,
                        help='Comma-separated whitelist of providers for `search run` '
                             '(e.g. "searxng,brave"). Default: all configured.',
                        default=None,
                        nargs='?')
    args = parser.parse_args()
    # Always convert lang to a list
    if hasattr(args, "lang") and isinstance(args.lang, str):
        args.lang = [l.strip() for l in args.lang.split(",") if l.strip()]
    # Optional: switch the SQLite file before any model operation
    if getattr(args, 'db', None):
        _switch_database(args.db)
    dispatch(args)


def _switch_database(db_path: str) -> None:
    """Re-bind the global Peewee database to the given SQLite file.

    Called from command_input when the user passes --db PATH. Preserves
    the same pragma set as the default initialization in mwi.model.
    """
    import os
    from . import model
    abs_path = os.path.abspath(db_path)
    if not os.path.exists(abs_path):
        raise SystemExit(f'--db: file not found: {abs_path}')
    pragmas = {
        'journal_mode': 'wal',
        'cache_size': -1 * 512000,
        'foreign_keys': 1,
        'ignore_check_constrains': 0,
        'synchronous': 0,
    }
    if not model.DB.is_closed():
        model.DB.close()
    model.DB.init(abs_path, pragmas=pragmas)
    print(f'Using database: {abs_path}')


def dispatch(args):
    """Dispatch parsed arguments to the appropriate application controller.

    Maps object-verb combinations to controller methods and handles nested
    commands (e.g., 'land llm validate'). Validates that the requested
    object and action exist before calling.

    Args:
        args: argparse.Namespace containing parsed command-line arguments.
            Must include 'object' and 'verb' attributes at minimum.

    Returns:
        The return value from the called controller method, typically None
        for side-effect operations like database updates or exports.

    Raises:
        ValueError: If the specified object is not recognized or if a nested
            command is missing its required subverb.

    Notes:
        The controller mapping supports both flat commands (e.g., 'land list')
        and nested commands (e.g., 'land llm validate'). Nested commands
        require a subverb argument to identify the specific action.
    """
    controllers = {
        'db': {
            'setup': DbController.setup,
            'migrate': DbController.migrate,
            'fix_archive_domains': DbController.fix_archive_domains
        },
        'domain': {
            'crawl': DomainController.crawl
        },
        'land': {
            'list':     LandController.list,
            'create':   LandController.create,
            'delete':   LandController.delete,
            'crawl':    LandController.crawl,
            'readable': LandController.readable,
            'export':   LandController.export,
            'addterm':  LandController.addterm,
            'relemm':   LandController.relemm,
            'addurl':   LandController.addurl,
            'urlist':   LandController.urlist,
            'consolidate': LandController.consolidate,
            'normalize': LandController.normalize,
            'medianalyse': LandController.medianalyse,
            'media_stats': LandController.media_stats,
            'preview_deletion': LandController.preview_deletion,
            'reanalyze': LandController.reanalyze,
            'seorank':  LandController.seorank,
            # Nested commands for LLM features
            'llm': {
                'validate': LandController.llm_validate,
            },
        },
        'tag': {
            'export': TagController.export,
        },
        'embedding': {
            'generate': EmbeddingController.generate,
            'similarity': EmbeddingController.similarity,
            'check': EmbeddingController.check,
            'reset': EmbeddingController.reset,
        },
        'heuristic': {
            'update': HeuristicController.update
        },
        'search': {
            'run':   SearchController.run,
            'list':  SearchController.list,
            'usage': SearchController.usage,
            'check': SearchController.check,
        },
    }
    controller = controllers.get(args.object)
    if controller:
        action = controller.get(args.verb)
        # Support nested verbs: e.g. controllers['land']['llm']['validate']
        if isinstance(action, dict):
            subverb = getattr(args, 'subverb', None)
            if not subverb:
                raise ValueError("Missing sub-verb for nested command (e.g. 'land llm validate')")
            return call(action.get(subverb), args)
        return call(action, args)
    raise ValueError("Invalid object {}".format(args.object))


def call(func, args):
    """Execute a controller function with the provided arguments.

    Validates that the function is callable before execution and provides
    informative error messages if the action is invalid.

    Args:
        func: The controller method to execute. Must be a callable object.
        args: argparse.Namespace containing command arguments to pass to
            the controller method.

    Returns:
        The return value from the executed controller method.

    Raises:
        ValueError: If func is not callable, includes the attempted verb
            and object in the error message.

    Notes:
        This function serves as a safety wrapper around controller method
        calls, ensuring that only valid callable objects are invoked and
        providing clear error messages for debugging.
    """
    if callable(func):
        return func(args)
    raise ValueError("Invalid action call {} on object {}".format(args.verb, args.object))
