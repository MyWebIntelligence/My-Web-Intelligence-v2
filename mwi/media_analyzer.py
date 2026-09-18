import io
import hashlib
import aiohttp
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans
from typing import Dict, Any, Optional

# Perceptual fingerprint geometry (R02 lot B). dHash compares each pixel with
# its right-hand neighbour, so the resize is one column WIDER than it is tall:
# 9x8 pixels give 8 comparisons per row over 8 rows = 64 bits = 16 hex chars.
_DHASH_SIZE = (9, 8)
_DHASH_BITS = 64


def perceptual_hash(image) -> Optional[str]:
    """Return the 64-bit dHash of `image` as 16 hex characters, or None.

    Answers "is this the SAME IMAGE?" where `image_hash` (SHA-256 of the
    bytes) answers "is this the SAME FILE?". A photo reprinted by another
    outlet after a recompression or a resize keeps a very close dHash and gets
    a completely unrelated SHA-256 — measuring that circulation is the point.

    Method: grayscale, resize to 9x8 with LANCZOS (which averages away
    compression noise), then one bit per pair of horizontally adjacent pixels,
    set when the left one is brighter. Relative comparisons, so the
    fingerprint is insensitive to overall brightness and to the scale.

    No new dependency: `imagehash` was dropped from the project in June 2026
    as a pip-freeze leftover nothing imported, and this is fifteen lines of
    Pillow. numpy is available but pointless for 64 comparisons.

    NEVER raises: anything Pillow cannot open — an SVG, a truncated file, a
    video — returns None, and the caller keeps the media row (with its
    SHA-256, which is computed before the image is even opened).
    """
    try:
        # Image.Resampling.LANCZOS, not the Image.LANCZOS alias: the alias
        # is absent from the type stubs. Pillow floor is 10.0.
        resized = image.convert('L').resize(_DHASH_SIZE,
                                            Image.Resampling.LANCZOS)
    except Exception:
        return None

    try:
        # tobytes(), not getdata(): in mode 'L' it yields exactly
        # width * height bytes in row-major order, and getdata() is deprecated
        # in Pillow 14 (which would put a warning in every test run).
        pixels = resized.tobytes()
    except Exception:
        return None

    width, height = _DHASH_SIZE
    bits = 0
    index = 0
    for row in range(height):
        offset = row * width
        for col in range(width - 1):
            if pixels[offset + col] > pixels[offset + col + 1]:
                bits |= 1 << index
            index += 1
    return '%016x' % bits


def hamming_distance(a: Optional[str], b: Optional[str]) -> int:
    """Number of differing bits between two dHash strings.

    A missing fingerprint is infinitely far from everything (returns
    _DHASH_BITS + 1): a media that was never analysed must never be reported
    as a near-duplicate, and every database is in that state until the first
    re-analysis after migration 016.
    """
    if not a or not b:
        return _DHASH_BITS + 1
    try:
        return bin(int(a, 16) ^ int(b, 16)).count('1')
    except (TypeError, ValueError):
        return _DHASH_BITS + 1


def generer_palette_web_safe():
    """Generate the 216 RGB colors of the Web Safe palette.

    Returns:
        List of (r, g, b) tuples representing web-safe colors.

    Note:
        Uses standard web-safe levels: 0, 51, 102, 153, 204, 255.
    """
    niveaux = [0, 51, 102, 153, 204, 255]
    return [(r, g, b) for r in niveaux for g in niveaux for b in niveaux]


def distance_rgb(c1, c2):
    """Calculate squared Euclidean distance between two RGB colors.

    Args:
        c1: First RGB color as (r, g, b) tuple.
        c2: Second RGB color as (r, g, b) tuple.

    Returns:
        Squared Euclidean distance as float.
    """
    return sum((a - b) ** 2 for a, b in zip(c1, c2))


def convertir_vers_web_safe(rgb):
    """Convert an RGB color to its nearest Web Safe palette equivalent.

    Args:
        rgb: RGB color as (r, g, b) tuple.

    Returns:
        Nearest web-safe RGB color as (r, g, b) tuple.
    """
    palette = generer_palette_web_safe()
    return min(palette, key=lambda c: distance_rgb(rgb, c))


class MediaAnalyzer:
    """Media analyzer with asynchronous processing capabilities.

    Attributes:
        session: aiohttp ClientSession for async HTTP requests.
        settings: Configuration dictionary for analysis parameters.
        max_size: Maximum file size in bytes for media downloads.
    """

    def __init__(self, session: aiohttp.ClientSession, settings: Dict[str, Any]):
        """Initialize MediaAnalyzer with session and settings.

        Args:
            session: Active aiohttp ClientSession for downloads.
            settings: Configuration dict with media analysis parameters.
        """
        self.session = session
        self.settings = settings
        self.max_size = self.settings.get('media_max_file_size', 10 * 1024 * 1024)

    async def analyze_image(self, url: str) -> Dict[str, Any]:
        """Perform comprehensive image analysis.

        Args:
            url: Image URL to download and analyze.

        Returns:
            Dictionary containing image metadata, dimensions, colors, EXIF,
            hash, and any error messages.

        Note:
            Downloads image with size limit, extracts properties, dominant
            colors, web-safe colors, and EXIF metadata.
        """
        result: Dict[str, Any] = {
            'error': None,
            'width': None,
            'height': None,
            'format': None,
            'file_size': None,
            'color_mode': None,
            'has_transparency': False,
            'aspect_ratio': None,
            'exif_data': None,
            'image_hash': None,
            'perceptual_hash': None,
            'dominant_colors': [],
            'websafe_colors': []
        }

        try:
            # Téléchargement avec limite de taille
            async with self.session.get(url) as response:
                if response.content_length and response.content_length > self.max_size:
                    raise ValueError(f"Taille dépassée ({response.content_length} bytes)")

                content = await response.read()
                if len(content) > self.max_size:
                    raise ValueError(f"Taille réelle dépassée ({len(content)} bytes)")

                result['file_size'] = len(content)

                # Empreinte CRYPTOGRAPHIQUE des octets, pas perceptuelle.
                # Elle répond à « est-ce le MÊME FICHIER ? » : ré-encoder la
                # même image à un autre niveau de compression donne un hash
                # sans rapport. « Est-ce la MÊME IMAGE ? » est la question de
                # `perceptual_hash` (dHash), calculée plus bas.
                # Calculée AVANT Image.open : un média illisible par Pillow
                # garde donc son image_hash.
                result['image_hash'] = hashlib.sha256(content).hexdigest()

                # Analyse avec PIL
                with Image.open(io.BytesIO(content)) as img:
                    # Empreinte PERCEPTUELLE (dHash) : « est-ce la même
                    # image ? ». Calculée en premier pour qu'un échec plus
                    # loin (couleurs, EXIF) ne la fasse pas perdre.
                    result['perceptual_hash'] = perceptual_hash(img)
                    self._analyze_image_properties(img, result)
                    self._extract_colors(img, result)
                    self._extract_exif(img, result)

        except Exception as e:
            result['error'] = str(e)

        return result

    def _analyze_image_properties(self, img: Image.Image, result: Dict):
        """Extract basic image properties.

        Args:
            img: PIL Image object to analyze.
            result: Dictionary to update with extracted properties.

        Note:
            Updates result with width, height, format, color mode,
            transparency, and aspect ratio.
        """
        result.update({
            'width': img.width,
            'height': img.height,
            'format': img.format,
            'color_mode': img.mode,
            'has_transparency': self._has_transparency(img),
            'aspect_ratio': round(img.width / img.height, 2) if img.height else 0
        })

    def _has_transparency(self, img: Image.Image) -> bool:
        """Detect if image contains transparency.

        Args:
            img: PIL Image object to check.

        Returns:
            True if image has any transparent pixels, False otherwise.

        Note:
            Only checks images with alpha channel (RGBA, LA modes).
        """
        if img.mode in ('RGBA', 'LA'):
            alpha = img.getchannel('A')
            # tobytes(): one byte per pixel in mode 'A', and unlike
            # getdata() it is both typed and not deprecated.
            return any(pixel < 255 for pixel in alpha.tobytes())
        return False

    def _extract_colors(self, img: Image.Image, result: Dict[str, Any]):
        """Extract dominant colors using K-means clustering.

        Args:
            img: PIL Image object to analyze.
            result: Dictionary to update with color information.

        Note:
            Resizes image to 100x100 for efficiency, clusters pixels into
            dominant colors, computes percentages, and converts to web-safe
            palette. Updates result with 'dominant_colors' and 'websafe_colors'.
        """
        n_colors = self.settings.get('media_n_dominant_colors', 5)
        try:
            # Réduire la taille pour le traitement
            img = img.resize((100, 100)).convert('RGB')
            pixels = np.array(img).reshape(-1, 3)

            # Clustering
            kmeans = KMeans(n_clusters=n_colors, n_init='auto', random_state=42)
            kmeans.fit(pixels)

            # Compter les occurrences
            counts = np.bincount(kmeans.labels_)
            total = sum(counts)

            # Tri par fréquence
            sorted_colors = sorted(zip(kmeans.cluster_centers_, counts),
                                   key=lambda x: x[1], reverse=True)

            # Formatage des résultats
            dominant_colors = [{
                'rgb': tuple(map(int, color)),
                'percentage': round(count / total * 100, 2)
            } for color, count in sorted_colors]

            result['dominant_colors'] = dominant_colors

            # Conversion en couleurs web safe
            websafe_palette = {}
            for item in dominant_colors:
                websafe_color = convertir_vers_web_safe(item['rgb'])
                websafe_hex = '#%02x%02x%02x' % websafe_color
                if websafe_hex not in websafe_palette:
                    websafe_palette[websafe_hex] = 0
                websafe_palette[websafe_hex] += item['percentage']

            result['websafe_colors'] = websafe_palette

        except Exception as e:
            result['error'] = f"Erreur d'analyse couleur: {str(e)}"

    def _extract_exif(self, img: Image.Image, result: Dict[str, Any]):
        """Extract EXIF metadata from image.

        Args:
            img: PIL Image object to analyze.
            result: Dictionary to update with EXIF data.

        Note:
            Extracts standard EXIF fields: ImageWidth, ImageLength, Make,
            Model, DateTime. Only includes non-null values.
        """
        try:
            exif_data = img.getexif()
            if exif_data:
                exif = {
                    "ImageWidth": exif_data.get(256),
                    "ImageLength": exif_data.get(257),
                    "Make": exif_data.get(271),
                    "Model": exif_data.get(272),
                    "DateTime": exif_data.get(306),
                }
                result['exif_data'] = {k: v for k, v in exif.items() if v is not None}
        except Exception as e:
            # Ne pas écraser une erreur précédente
            if not result.get('error'):
                result['error'] = f"Erreur EXIF: {str(e)}"
