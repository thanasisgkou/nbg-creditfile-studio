import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, TextLayer } from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Download,
  Minus,
  Plus,
  Scan,
  FileText,
} from "lucide-react";
import type { Source } from "./api";
import "./pdf-text.css";
GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfReader({
  url,
  source,
  title = "Έγγραφο πηγής",
}: {
  url: string;
  source?: Source | null;
  title?: string;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy>();
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(600);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [rendered, setRendered] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayer = useRef<HTMLDivElement>(null);
  const paper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setPdf(undefined);
    setError("");
    setBusy(true);
    setRendered(false);
    const saved = sessionStorage.getItem("pdf:" + url);
    const savedState = saved ? JSON.parse(saved) : {};
    setPage(savedState.page ?? 1);
    setZoom(savedState.zoom ?? 1);
    const task = getDocument({ url });
    let active = true;
    task.promise
      .then((doc) => {
        if (active) {
          setPdf(doc);
          setPage((p) => Math.min(p, doc.numPages));
        }
      })
      .catch(() => {
        if (active) {
          setError(
            "Το PDF δεν φορτώθηκε. Μπορείτε να το ανοίξετε σε νέα καρτέλα.",
          );
          setBusy(false);
        }
      });
    return () => {
      active = false;
      void task.destroy();
    };
  }, [url]);
  useEffect(() => {
    if (source) setPage(source.page);
  }, [source, pdf]);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(200, entries[0].contentRect.width - 40)),
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current || !textLayer.current || !paper.current) return;
    let active = true;
    let rendering:
      | ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]>
      | undefined;
    let layer: TextLayer | undefined;
    setBusy(true);
    setRendered(false);
    pdf
      .getPage(Math.min(Math.max(1, page), pdf.numPages))
      .then(async (p) => {
        if (!active || !canvas.current || !paper.current || !textLayer.current)
          return;
        const scale = (width / p.getViewport({ scale: 1 }).width) * zoom;
        const viewport = p.getViewport({ scale });
        const output = window.devicePixelRatio || 1;
        const surface = canvas.current;
        surface.width = Math.floor(viewport.width * output);
        surface.height = Math.floor(viewport.height * output);
        surface.style.width = viewport.width + "px";
        surface.style.height = viewport.height + "px";
        paper.current.style.width = viewport.width + "px";
        paper.current.style.height = viewport.height + "px";
        paper.current.style.setProperty("--scale-factor", String(scale));
        paper.current.style.setProperty("--total-scale-factor", String(scale));
        textLayer.current.replaceChildren();
        rendering = p.render({
          canvas: surface,
          canvasContext: surface.getContext("2d")!,
          viewport,
          transform: [output, 0, 0, output, 0, 0],
        });
        await rendering.promise;
        if (!active) return;
        layer = new TextLayer({
          textContentSource: await p.getTextContent(),
          container: textLayer.current!,
          viewport,
        });
        await layer.render();
        if (active) {
          setBusy(false);
          setRendered(true);
          setError("");
          sessionStorage.setItem("pdf:" + url, JSON.stringify({ page, zoom }));
        }
      })
      .catch((e) => {
        if (active && e.name !== "RenderingCancelledException") {
          setError("Η σελίδα δεν μπόρεσε να εμφανιστεί.");
          setBusy(false);
        }
      });
    return () => {
      active = false;
      rendering?.cancel();
      layer?.cancel();
    };
  }, [pdf, page, width, zoom, url]);
  useEffect(() => {
    if (!rendered || !source || page !== source.page) return;
    const selected = host.current?.querySelector(".pdf-highlight");
    if (selected && host.current) {
      const box = selected.getBoundingClientRect(),
        container = host.current.getBoundingClientRect();
      host.current.scrollTo({
        top:
          host.current.scrollTop +
          box.top -
          container.top -
          host.current.clientHeight / 2 +
          box.height / 2,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
    }
  }, [rendered, source, page]);
  const rects = source?.value_rectangles?.length
    ? source.value_rectangles
    : (source?.rectangles ?? []);
  return (
    <section className="pdf-reader" aria-label={title}>
      <div className="reader-title">
        <span>
          <FileText size={15} />
          {title}
        </span>
        <a
          className="icon-button"
          href={url}
          target="_blank"
          rel="noreferrer"
          aria-label="Άνοιγμα PDF σε νέα καρτέλα"
        >
          <ArrowUpRight size={17} />
        </a>
      </div>
      <div className="reader-toolbar">
        <div>
          <button
            className="icon-button"
            disabled={!pdf || page <= 1}
            onClick={() => setPage(page - 1)}
            aria-label="Προηγούμενη σελίδα"
          >
            <ChevronLeft size={16} />
          </button>
          <span>
            Σελ. <b>{page}</b> / {pdf?.numPages ?? "…"}
          </span>
          <button
            className="icon-button"
            disabled={!pdf || page >= pdf.numPages}
            onClick={() => setPage(page + 1)}
            aria-label="Επόμενη σελίδα"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <div>
          <button
            className="icon-button"
            disabled={zoom <= 0.6}
            onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
            aria-label="Σμίκρυνση"
          >
            <Minus size={15} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            className="icon-button"
            disabled={zoom >= 2.4}
            onClick={() => setZoom((z) => Math.min(2.4, z + 0.2))}
            aria-label="Μεγέθυνση"
          >
            <Plus size={15} />
          </button>
          <button
            className="icon-button"
            onClick={() => setZoom(1)}
            aria-label="Προσαρμογή στο πλάτος"
          >
            <Scan size={16} />
          </button>
          <a href={url} download className="icon-button" aria-label="Λήψη PDF">
            <Download size={15} />
          </a>
        </div>
      </div>
      <div
        className="pdf-scroll"
        ref={host}
        tabIndex={0}
        aria-label="Σελίδες PDF"
      >
        {busy && (
          <div className="reader-loading" role="status">
            <span className="spinner" /> Φόρτωση σελίδας
          </div>
        )}
        {error && (
          <div className="inline-error" role="alert">
            {error}
          </div>
        )}
        <div
          className="pdf-paper"
          ref={paper}
          style={{ visibility: pdf ? "visible" : "hidden" }}
        >
          <canvas ref={canvas} aria-label={`Σελίδα ${page} του εγγράφου`} />
          <div className="textLayer" ref={textLayer} />
          {rendered &&
            source?.page === page &&
            rects.map((r, i) => (
              <span
                key={i}
                className="pdf-highlight"
                style={{
                  left: (r[0] / (source.page_width || 1)) * 100 + "%",
                  top: (r[1] / (source.page_height || 1)) * 100 + "%",
                  width: ((r[2] - r[0]) / (source.page_width || 1)) * 100 + "%",
                  height:
                    ((r[3] - r[1]) / (source.page_height || 1)) * 100 + "%",
                }}
              />
            ))}
        </div>
      </div>
      {source && (
        <div className="source-excerpt">
          <span className="eyebrow">
            {rects.length
              ? "ΕΝΤΟΠΙΣΜΕΝΗ ΠΗΓΗ"
              : "ΤΕΚΜΗΡΙΩΜΕΝΟ ΑΠΟΣΠΑΣΜΑ · ΧΩΡΙΣ ΑΚΡΙΒΕΣ HIGHLIGHT"}
          </span>
          <p>{source.quote || source.excerpt}</p>
        </div>
      )}
    </section>
  );
}
