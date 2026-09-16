#!/usr/bin/env python
"""Manga Translate CLI — download, translate, and generate PDFs.

Uses the shared ``core/`` modules so that CLI and web API share identical logic.
"""
from __future__ import annotations

import argparse
import asyncio
import queue
import textwrap
import threading
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from core.downloader import download_images
from core.models import PageImage, read_json, slugify, write_json
from core.parsers import parse_source
from core.pdf import make_image_pdf, make_long_strip_pdf
from core.translate import lens_translate_work_dir


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def command_go(args) -> None:
    """Download + Google Lens translate + long-strip PDF (single command)."""
    title, pages = parse_source(args.url)
    work_dir = Path(args.output or Path("output") / slugify(title))
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_pages = download_images(pages, work_dir, workers=args.download_workers)
    write_json(
        work_dir / "manifest.json",
        {"source": args.url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
    )
    print(f"Saved {len(manifest_pages)} images to {work_dir / 'images'}")

    results = asyncio.run(
        lens_translate_work_dir(
            work_dir, lang=args.lang, concurrency=args.lens_workers,
            verbose=args.verbose, max_retries=args.max_retries,
        )
    )
    ok = sum(1 for r in results if r.get("translated_file"))
    print(f"Lens: {ok}/{len(results)} translated.")
    output_pdf = make_long_strip_pdf(
        work_dir, None, translated=True, chunk_size=args.chunk_size, width_mm=args.width_mm
    )
    print(f"PDF: {output_pdf}")


def command_from_url(args) -> None:
    title, pages = parse_source(args.url)
    work_dir = Path(args.output or Path("output") / slugify(title))
    work_dir.mkdir(parents=True, exist_ok=True)

    manifest_pages = download_images(pages, work_dir, workers=args.download_workers)
    write_json(
        work_dir / "manifest.json",
        {"source": args.url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
    )
    print(f"Saved {len(manifest_pages)} images to {work_dir / 'images'}")

    if args.lens_long_pdf:
        results = asyncio.run(
            lens_translate_work_dir(
                work_dir, lang=args.lang, limit=args.limit,
                force=args.force_lens, concurrency=args.lens_workers,
                verbose=args.verbose,
            )
        )
        ok = sum(1 for row in results if row.get("translated_file"))
        failed = len(results) - ok
        print(f"Lens translated {ok} page(s), failed {failed}. Metadata: {work_dir / 'lens_translations.json'}")
        output_pdf = make_long_strip_pdf(
            work_dir,
            Path(args.long_output) if args.long_output else None,
            translated=True, chunk_size=args.chunk_size, width_mm=args.width_mm,
        )
        print(f"Long PDF written to {output_pdf}")


def command_chapter_range(args) -> None:
    raw_base = args.base_url
    base_url = raw_base if raw_base.endswith("-") else raw_base.rstrip("/") + "/"
    failed_chapters: list[int] = []

    ready: queue.Queue[object] = queue.Queue(maxsize=2)
    SENTINEL = object()

    def producer():
        for n in range(args.start, args.end + 1):
            chapter_url = f"{base_url}chapter-{n}/"
            try:
                title, pages = parse_source(chapter_url)
                chapter_slug = urlparse(chapter_url).path.strip("/").split("/")[-1] or f"chapter-{n}"
                if args.output_prefix:
                    work_dir = Path(f"{args.output_prefix}_{n}")
                else:
                    work_dir = Path("output") / chapter_slug
                work_dir.mkdir(parents=True, exist_ok=True)
                manifest_pages = download_images(pages, work_dir, workers=8, quiet=True)
                write_json(
                    work_dir / "manifest.json",
                    {"source": chapter_url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
                )
                ready.put({
                    "n": n, "url": chapter_url, "title": title,
                    "work_dir": work_dir, "chapter_slug": chapter_slug,
                    "downloaded": len(manifest_pages),
                })
            except Exception as exc:
                ready.put({"n": n, "url": chapter_url, "error": exc})
        ready.put(SENTINEL)

    producer_thread = threading.Thread(target=producer, daemon=True)
    producer_thread.start()

    bar = "─" * 60
    total = args.end - args.start + 1
    processed = 0

    while True:
        item = ready.get()
        if item is SENTINEL:
            break
        n = item["n"]
        processed += 1
        print(f"\n┌{bar}")
        print(f"│ 📖 Chapter {n}  ({processed}/{total})")
        print(f"│ {item['url']}")
        print(f"└{bar}")

        if "error" in item:
            print(f"  ❌ Parse/download failed: {item['error']}")
            failed_chapters.append(n)
            continue

        work_dir = item["work_dir"]
        chapter_slug = item["chapter_slug"]
        print(f"  📥 Downloaded {item['downloaded']} pages → {work_dir.name}/images")

        if args.lens_long_pdf:
            try:
                results = asyncio.run(
                    lens_translate_work_dir(work_dir, lang=args.lang, force=False, concurrency=4, verbose=False)
                )
                ok = sum(1 for row in results if row.get("translated_file"))
                failed_pages = [int(r["page"]) for r in results if not r.get("translated_file")]

                if failed_pages:
                    print(f"  ⚠️  Lens: {ok}/{len(results)} OK · failed pages {failed_pages} → retrying...")
                    retry_results = asyncio.run(
                        lens_translate_work_dir(
                            work_dir, lang=args.lang, force=True, concurrency=4,
                            verbose=False, max_retries=3, only_pages=set(failed_pages),
                        )
                    )
                    retry_ok = sum(1 for r in retry_results if r.get("translated_file"))
                    still_failed = [int(r["page"]) for r in retry_results if not r.get("translated_file")]
                    print(f"  🔁 Retry: {retry_ok}/{len(retry_results)} recovered" + (f" · still failing: {still_failed}" if still_failed else ""))
                    if still_failed:
                        failed_chapters.append(n)
                        continue
                else:
                    print(f"  ✅ Lens translated {ok}/{len(results)} pages")

                pdf_dir = Path("output") / "pdfs"
                pdf_dir.mkdir(parents=True, exist_ok=True)
                output_pdf = make_long_strip_pdf(
                    work_dir, pdf_dir / f"{chapter_slug}.pdf",
                    translated=True, chunk_size=args.chunk_size, width_mm=args.width_mm,
                )
                print(f"  📄 PDF → {output_pdf}")
            except Exception as exc:
                print(f"  ❌ Lens/PDF failed: {exc}")
                failed_chapters.append(n)

    producer_thread.join(timeout=5)

    print(f"\n{'═' * 60}")
    ok_count = total - len(failed_chapters)
    print(f"  Done. {ok_count}/{total} chapters succeeded.")
    if failed_chapters:
        print(f"  ⚠️  Failed chapters: {failed_chapters}")
        print(f"  💡 Tip: run `lens-retry output/<chapter-slug>` to retry those")
    print(f"{'═' * 60}")


def command_batch(args) -> None:
    urls: list[str] = []
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    urls.extend(args.urls or [])
    if not urls:
        raise RuntimeError("No URLs provided. Pass --file <path> or extra positional URLs.")

    print(f"Batch processing {len(urls)} URL(s)")
    failures: list[tuple[str, str]] = []
    for index, url in enumerate(urls, start=1):
        print(f"\n[{index}/{len(urls)}] {url}")
        try:
            title, pages = parse_source(url)
            work_dir = Path("output") / slugify(title)
            work_dir.mkdir(parents=True, exist_ok=True)
            manifest_pages = download_images(pages, work_dir, workers=args.download_workers)
            write_json(
                work_dir / "manifest.json",
                {"source": url, "title": title, "page_count": len(manifest_pages), "pages": manifest_pages},
            )
            if args.lens_long_pdf:
                results = asyncio.run(
                    lens_translate_work_dir(
                        work_dir, lang=args.lang, concurrency=args.lens_workers,
                        verbose=args.verbose, max_retries=args.max_retries,
                    )
                )
                ok = sum(1 for row in results if row.get("translated_file"))
                failed = len(results) - ok
                print(f"  Lens translated {ok} page(s), failed {failed}.")
                make_long_strip_pdf(work_dir, None, translated=True, chunk_size=args.chunk_size, width_mm=args.width_mm)
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            failures.append((url, str(exc)))

    print(f"\nDone. {len(urls) - len(failures)} succeeded, {len(failures)} failed.")
    if failures:
        for url, err in failures:
            print(f"  FAIL {url}: {err}")


def command_lens(args) -> None:
    work_dir = Path(args.work_dir)
    results = asyncio.run(
        lens_translate_work_dir(
            work_dir, lang=args.lang, limit=args.limit, force=args.force,
            concurrency=args.workers, verbose=args.verbose, max_retries=args.max_retries,
        )
    )
    ok = sum(1 for row in results if row.get("translated_file"))
    failed = len(results) - ok
    print(f"Lens translated {ok} page(s), failed {failed}. Metadata: {work_dir / 'lens_translations.json'}")
    if args.make_pdf:
        output_pdf = make_image_pdf(work_dir, Path(args.output) if args.output else None, translated=True)
        print(f"PDF written to {output_pdf}")
    if args.make_long_pdf:
        output_pdf = make_long_strip_pdf(
            work_dir, Path(args.long_output) if args.long_output else None,
            translated=True, chunk_size=args.chunk_size, width_mm=args.width_mm,
        )
        print(f"Long PDF written to {output_pdf}")


def command_lens_retry(args) -> None:
    work_dir = Path(args.work_dir)
    failed_path = work_dir / "lens_failed.json"
    failed_pages = read_json(failed_path, [])
    if not failed_pages:
        print("No failed pages to retry.")
        return
    print(f"Retrying {len(failed_pages)} failed page(s): {failed_pages}")
    results = asyncio.run(
        lens_translate_work_dir(
            work_dir, lang=args.lang, force=True, concurrency=args.workers,
            verbose=args.verbose, max_retries=args.max_retries,
            only_pages=set(int(p) for p in failed_pages),
        )
    )
    ok = sum(1 for row in results if row.get("translated_file"))
    failed = len(results) - ok
    print(f"Retry: {ok} succeeded, {failed} still failing.")


def command_make_image_pdf(args) -> None:
    output_pdf = make_image_pdf(
        Path(args.work_dir), Path(args.output) if args.output else None,
        translated=not args.original,
    )
    print(f"PDF written to {output_pdf}")


def command_make_long_pdf(args) -> None:
    output_pdf = make_long_strip_pdf(
        Path(args.work_dir), Path(args.output) if args.output else None,
        translated=not args.original, chunk_size=args.chunk_size,
        width_mm=args.width_mm, max_page_height_mm=getattr(args, "max_page_height_mm", 0),
    )
    print(f"Long PDF written to {output_pdf}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download manga pages, translate to Thai via Google Lens, and build a reading PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(r"""
            Examples:
              python cli.py go "https://mangadex.org/chapter/..."
              python cli.py from-url "https://weebcentral.com/chapters/..." --lens-long-pdf
              python cli.py chapter-range "https://mangablaze.com/manga/<slug>/" 1 5 --lens-long-pdf
              python cli.py batch --file urls.txt --lens-long-pdf
              python cli.py lens ".\output\chapter-id" --make-long-pdf
              python cli.py lens-retry ".\output\chapter-id"
              python cli.py make-long-pdf ".\output\chapter-id" --max-page-height-mm 800
        """),
    )
    subparsers = parser.add_subparsers(required=True)

    from_url = subparsers.add_parser("from-url")
    from_url.add_argument("url")
    from_url.add_argument("--output")
    from_url.add_argument("--lens-long-pdf", action="store_true")
    from_url.add_argument("--lang", default="th")
    from_url.add_argument("--force-lens", action="store_true")
    from_url.add_argument("--lens-workers", type=int, default=4)
    from_url.add_argument("--download-workers", type=int, default=8)
    from_url.add_argument("--chunk-size", type=int, default=8)
    from_url.add_argument("--width-mm", type=float, default=190)
    from_url.add_argument("--long-output")
    from_url.add_argument("--verbose", action="store_true")
    from_url.add_argument("--limit", type=int)
    from_url.set_defaults(func=command_from_url)

    chapter_range = subparsers.add_parser("chapter-range", help="Download and translate a range of chapters")
    chapter_range.add_argument("base_url")
    chapter_range.add_argument("start", type=int)
    chapter_range.add_argument("end", type=int)
    chapter_range.add_argument("--output-prefix", default=None)
    chapter_range.add_argument("--lens-long-pdf", action="store_true")
    chapter_range.add_argument("--lang", default="th")
    chapter_range.add_argument("--chunk-size", type=int, default=8)
    chapter_range.add_argument("--width-mm", type=float, default=190)
    chapter_range.set_defaults(func=command_chapter_range)

    go = subparsers.add_parser("go", help="Download + Lens translate + build long PDF (one shot)")
    go.add_argument("url")
    go.add_argument("--output")
    go.add_argument("--lang", default="th")
    go.add_argument("--download-workers", type=int, default=8)
    go.add_argument("--lens-workers", type=int, default=4)
    go.add_argument("--max-retries", type=int, default=2)
    go.add_argument("--chunk-size", type=int, default=8)
    go.add_argument("--width-mm", type=float, default=190)
    go.add_argument("--verbose", action="store_true")
    go.set_defaults(func=command_go)

    batch = subparsers.add_parser("batch", help="Process many chapter URLs")
    batch.add_argument("urls", nargs="*")
    batch.add_argument("--file")
    batch.add_argument("--lens-long-pdf", action="store_true")
    batch.add_argument("--lang", default="th")
    batch.add_argument("--chunk-size", type=int, default=8)
    batch.add_argument("--width-mm", type=float, default=190)
    batch.add_argument("--lens-workers", type=int, default=4)
    batch.add_argument("--download-workers", type=int, default=8)
    batch.add_argument("--max-retries", type=int, default=2)
    batch.add_argument("--verbose", action="store_true")
    batch.set_defaults(func=command_batch)

    lens = subparsers.add_parser("lens")
    lens.add_argument("work_dir")
    lens.add_argument("--lang", default="th")
    lens.add_argument("--limit", type=int)
    lens.add_argument("--force", action="store_true")
    lens.add_argument("--workers", type=int, default=4)
    lens.add_argument("--verbose", action="store_true")
    lens.add_argument("--make-pdf", action="store_true")
    lens.add_argument("--make-long-pdf", action="store_true")
    lens.add_argument("--chunk-size", type=int, default=8)
    lens.add_argument("--width-mm", type=float, default=190)
    lens.add_argument("--output")
    lens.add_argument("--long-output")
    lens.add_argument("--max-retries", type=int, default=2)
    lens.set_defaults(func=command_lens)

    lens_retry = subparsers.add_parser("lens-retry", help="Retry pages listed in lens_failed.json")
    lens_retry.add_argument("work_dir")
    lens_retry.add_argument("--lang", default="th")
    lens_retry.add_argument("--workers", type=int, default=4)
    lens_retry.add_argument("--max-retries", type=int, default=3)
    lens_retry.add_argument("--verbose", action="store_true")
    lens_retry.set_defaults(func=command_lens_retry)

    image_pdf = subparsers.add_parser("make-image-pdf")
    image_pdf.add_argument("work_dir")
    image_pdf.add_argument("--output")
    image_pdf.add_argument("--original", action="store_true")
    image_pdf.set_defaults(func=command_make_image_pdf)

    long_pdf = subparsers.add_parser("make-long-pdf")
    long_pdf.add_argument("work_dir")
    long_pdf.add_argument("--output")
    long_pdf.add_argument("--original", action="store_true")
    long_pdf.add_argument("--chunk-size", type=int, default=8)
    long_pdf.add_argument("--width-mm", type=float, default=190)
    long_pdf.add_argument("--max-page-height-mm", type=float, default=0)
    long_pdf.set_defaults(func=command_make_long_pdf)

    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
