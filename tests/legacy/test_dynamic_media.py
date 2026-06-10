#!/usr/bin/env python3
"""
Script de test pour l'extraction dynamique des médias

Ce fichier peut être exécuté directement en tant que script ou via pytest.
"""
import asyncio
import sys
import os
import pytest

# Ajouter la racine du projet au PYTHONPATH pour les imports
tests_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(tests_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try imports - skip tests if dependencies unavailable
try:
    from mwi import model, core
    import settings
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    IMPORT_ERROR = str(e)

pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE,
    reason=f"Required imports not available: {IMPORT_ERROR if not IMPORTS_AVAILABLE else ''}"
)

@pytest.mark.asyncio
@pytest.mark.playwright
@pytest.mark.integration
async def test_dynamic_media_extraction():
    """
    Test l'extraction dynamique des médias sur une page web
    """
    print("=== Test d'extraction dynamique des médias ===\n")
    
    # Vérifier la configuration
    print(f"Configuration dynamic_media_extraction: {getattr(settings, 'dynamic_media_extraction', 'NON DÉFINI')}")
    print(f"Playwright disponible: {core.PLAYWRIGHT_AVAILABLE}")
    
    if not core.PLAYWRIGHT_AVAILABLE:
        print("\n❌ Playwright n'est pas disponible.")
        print("Veuillez installer Playwright avec:")
        print("1. pip install -r requirements.txt")
        print("2. python install_playwright.py")
        return False
    
    if not getattr(settings, 'dynamic_media_extraction', False):
        print("\n⚠️  L'extraction dynamique des médias est désactivée dans settings.py")
        print("Vous pouvez l'activer en définissant dynamic_media_extraction = True")
        return False
    
    print("\n✅ Tous les prérequis sont satisfaits.\n")
    
    # Créer une expression de test (sans l'enregistrer en base)
    class MockExpression:
        def __init__(self, url):
            self.url = url
            self.id = "TEST"
    
    # URL de test avec des images (utiliser une page publique connue pour avoir des images)
    test_urls = [
        "https://httpbin.org/html",  # Page simple avec HTML
        "https://example.com",       # Page très basique
    ]
    
    for test_url in test_urls:
        print(f"🔍 Test avec l'URL: {test_url}")
        
        try:
            # Créer une expression mock
            mock_expr = MockExpression(test_url)
            
            # Tester l'extraction dynamique
            print("   Lancement de l'extraction dynamique...")
            media_urls = await core.extract_dynamic_medias(test_url, mock_expr)
            
            print(f"   ✅ Extraction terminée. {len(media_urls)} médias trouvés:")
            for i, media_url in enumerate(media_urls, 1):
                print(f"      {i}. {media_url}")
            
            if not media_urls:
                print("      (Aucun média trouvé - normal pour certaines pages)")
            
        except Exception as e:
            print(f"   ❌ Erreur lors de l'extraction: {e}")
        
        print()
    
    print("=== Test terminé ===")
    return True

@pytest.mark.asyncio
async def test_url_resolution():
    """
    Test la fonction de résolution des URLs
    """
    print("=== Test de résolution des URLs ===\n")
    
    test_cases = [
        # (base_url, relative_url, expected_result)
        ("https://example.com/page", "/images/photo.JPG", "https://example.com/images/photo.jpg"),
        ("https://example.com/blog/", "../assets/image.PNG", "https://example.com/assets/image.png"),
        ("https://example.com", "https://other.com/img.gif", "https://other.com/img.gif"),
        ("https://example.com/path/", "relative/photo.JPEG", "https://example.com/path/relative/photo.jpeg"),
    ]
    
    for base_url, relative_url, expected in test_cases:
        result = core.resolve_url(base_url, relative_url)
        status = "✅" if result == expected else "❌"
        print(f"{status} Base: {base_url}")
        print(f"     Relative: {relative_url}")
        print(f"     Résultat: {result}")
        print(f"     Attendu:  {expected}")
        print()
        assert result == expected
    
    print("=== Test de résolution terminé ===\n")

def main():
    """
    Fonction principale
    """
    print("MyWebIntelligence - Test d'extraction dynamique des médias\n")
    
    # Test synchrone de résolution des URLs
    asyncio.run(test_url_resolution())
    
    # Test asynchrone d'extraction dynamique
    success = asyncio.run(test_dynamic_media_extraction())
    
    if success:
        print("\n🎉 Tous les tests ont été exécutés.")
    else:
        print("\n⚠️  Certains tests n'ont pas pu être exécutés en raison de dépendances manquantes.")

if __name__ == "__main__":
    main()
