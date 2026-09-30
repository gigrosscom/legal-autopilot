**[🟡] SEO и превью ссылок — нет OG/Twitter-тегов, canonical, robots.txt, sitemap.xml**
Факт: в HTML главной нет `og:*`, `twitter:*`, `rel=canonical`, `hreflang`; `/robots.txt` и `/sitemap.xml` → 404; description:
«…а когда нужно — поможет найти юриста» (юристов на сайте нет).
Влияние: ссылка в Telegram/WhatsApp/Instagram без картинки; AWS Activate проверяет сайт роботом (team/registrations/aws-activate.md §4).
Ожидаемый: og:title/description/image 1200×630, twitter:card, canonical, robots.txt + sitemap.xml, description без юриста.
Метки: bug, major, seo, smm
