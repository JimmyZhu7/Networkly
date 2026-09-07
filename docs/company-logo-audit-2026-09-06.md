# Company Logo Audit — 6 September 2026

## Result

The library contains 138 reviewed company logos. The follow-up replaced all 38 identifiable firms that still had initials after the initial 100-logo pass. No AI-generated recreations remain in the shipped library.

Sources include company websites, company-published press releases and filings, and published logo references hosted by Wikimedia. Each asset has its actual source URL, reference page, review date, and SHA-256 fingerprint in `networkly_web/static/img/firm-logos/sources.json`. Reference-hosted artwork is not described as downloaded from a company website.

The resolver requires a reviewed record and matching bytes. Unreviewed files and legacy media uploads cannot bypass that check. All existing logo surfaces share the resolver.

## Artwork Review

Original artwork was proportionally fitted; empty padding was trimmed. Vector files were rasterized only where they contained no font-dependent text, avoiding font substitutions. Artwork was not redrawn, stretched, or recolored. Haitong's official white artwork sits on a dark tile so it remains visible.

Rejected candidates included partner logos, unrelated social icons, outdated brand variants, blank images, and a dictionary image returned for an incorrect Sixth Street reference. The accepted Neuberger wordmark matches the company's 2026 brand update; Carlyle uses its current company-published wordmark rather than the older “The Carlyle Group” reference.

The 38 replacement marks were individually inspected in review sheets at larger and 32-pixel display sizes. Some firms use wide wordmarks, which necessarily render smaller within a square tile; their company names remain separately visible in the interface.

## ICC Bank

The remaining entry, `icc-bank` (local record 209), had no domains, opportunities, dates, contacts, user selections, tasks, proposals, or application events. Its identity could not be established, and the user did not recognize it. It was marked inactive locally without deleting the record. No unrelated bank's artwork was assigned.

Onboarding, Settings, and import mapping exclude explicitly inactive firms from new selections. Target-only firms remain available. Existing tracked relationships remain available. This local data cleanup is not a claim that a production database was changed.

## Maintenance

Use source-traceable artwork, review the correct legal/brand identity and small-size appearance, and update the fingerprint only after review. Never automatically publish a candidate based on its filename or dimensions. Restart application workers after changing the library. The older media-fetch command stages media and does not publish it.

## Validation

- 39 targeted logo, provenance, fallback, and firm-picker tests passed in a separate test database.
- The registry check confirms that every shipped PNG has a reviewed source record and matching bytes.
- WebKit rendered Settings successfully with every requested logo image loaded and no broken images. All 138 selectable firms resolve to reviewed artwork.
- The 9 firm-picker tests passed again after explicitly checking that target-only firms remain selectable while inactive entries are excluded.
