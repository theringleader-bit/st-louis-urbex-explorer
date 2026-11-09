ST. LOUIS EXPLORER — AUTOMATED INTERNET RESEARCH

This package uses your existing STL_Explorer_Map_v2.html, STL_Properties_v2.csv and STL_Urbex_Research_Initial.csv.

1. Create a GitHub repository (public only if you want to publish the map).
2. Upload the package files, preserving .github/workflows/update-research.yml.
3. In the repository's Actions tab, enable workflows if prompted.
4. Run 'Refresh St Louis urbex research' once via 'Run workflow'.
5. The daily workflow will commit STL_Explorer_Auto_Research.html and urbex_research_updates.json.
6. To view from your phone, enable GitHub Pages under Settings > Pages, Source: Deploy from a branch, main, root. Open the published STL_Explorer_Auto_Research.html page.

This first automation checks public Google News RSS queries daily. It links research leads and does NOT automatically claim that an article describes a specific parcel. It does NOT automatically query Reddit, whose Data API requires approved access. It does NOT refresh the city registry; that is a separate future job and needs reliable source endpoint verification.

This is a prototype, not a comprehensive scan of every property. Links and dates depend on source availability. No legal-access claims are made.
