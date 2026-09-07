import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  CircleAlert,
  Clock3,
  FileCheck2,
  FilePlus2,
  Files,
  FileText,
  FolderOpen,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
  PanelLeftClose,
  Pencil,
  RefreshCw,
  History,
} from "lucide-react";
import {
  api,
  BASE,
  canonicalMoney,
  command,
  dateLabel,
  kindLabel,
  post,
  valueLabel,
} from "./api";
import type { CaseRow, FieldValue, Source, Workspace } from "./api";
import PdfReader from "./Reader";
import { claimParts } from "./chatLinks";
import "@fontsource/ibm-plex-sans/greek-400.css";
import "@fontsource/ibm-plex-sans/greek-500.css";
import "@fontsource/ibm-plex-sans/greek-600.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "./style.css";

const client = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 15000, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
const titleMap: Record<string, string> = {
  overview: "Επισκόπηση",
  review: "Έλεγχος στοιχείων",
  documents: "Έγγραφα",
  bulletin: "Δελτίο προετοιμασίας",
};
const icons = {
  overview: LayoutDashboard,
  review: CheckCheck,
  documents: Files,
  bulletin: FileCheck2,
};
const useCases = () =>
  useQuery<CaseRow[]>({ queryKey: ["cases"], queryFn: () => api("/cases") });
const message = (e: unknown) =>
  e instanceof Error ? e.message : "Η ενέργεια δεν ολοκληρώθηκε.";

function Brand() {
  return (
    <Link
      className="brand"
      to="/"
      aria-label="Numbers Become Guidance — Φάκελοι"
    >
      <img
        className="brand-logo"
        src="/branding/nbg-logo.png"
        alt=""
        width={58}
        height={58}
      />
      <span className="brand-name">
        <span className="brand-word">
          <b>N</b>umbers
        </span>
        <span className="brand-word">
          <b>B</b>ecome
        </span>
        <span className="brand-word">
          <b>G</b>uidance
        </span>
      </span>
    </Link>
  );
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <span className={"badge " + tone}>
      <span />
      {children}
    </span>
  );
}
function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <FolderOpen size={38} />
      <h2>{title}</h2>
      {children}
    </div>
  );
}
function Loading() {
  return (
    <div className="page-loading" role="status">
      <LoaderCircle className="spin" size={24} /> Φόρτωση χώρου εργασίας…
    </div>
  );
}
function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="inline-error" role="alert">
      <CircleAlert size={17} />
      {message(error)}
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  busy = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = React.useId();
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      className="modal"
      aria-labelledby={titleId}
    >
      <header>
        <h2 id={titleId}>{title}</h2>
        <button
          className="icon-button"
          onClick={onClose}
          disabled={busy}
          aria-label="Κλείσιμο"
        >
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
function Shell() {
  const { data: cases = [] } = useCases();
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={"shell " + (collapsed ? "collapsed" : "")}>
      <aside className="sidebar">
        <Brand />
        <div className="nav-label">ΧΩΡΟΣ ΑΝΑΛΥΤΗ</div>
        <NavLink to="/" end className="nav-main">
          <FolderOpen size={19} />
          <span>Οι φάκελοί μου</span>
          <b>{cases.length}</b>
        </NavLink>
        <NavLink to="/new" className="nav-main">
          <FilePlus2 size={19} />
          <span>Νέος φάκελος</span>
        </NavLink>
        <div className="sidebar-rule" />
        <div className="nav-label">ΠΡΟΣΦΑΤΟΙ ΦΑΚΕΛΟΙ</div>
        <div className="recent-list">
          {cases.slice(0, 5).map((c) => (
            <Link key={c.id} to={"/cases/" + c.id + "/overview"}>
              <span className="case-dot" />
              <span>{c.name}</span>
            </Link>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="isolation">
            <ShieldCheck size={18} />
            <div>
              <b>Χώρος εργασίας</b>
              <small>Οι αλλαγές μένουν στο Studio</small>
            </div>
          </div>

          <div className="profile">
            <span>ΑΝ</span>
            <div>
              <b>Χώρος αναλυτή</b>
              <small>Τοπική συνεδρία</small>
            </div>
            <button
              className="icon-button"
              onClick={() => setCollapsed(!collapsed)}
              aria-label="Σύμπτυξη πλοήγησης"
            >
              <PanelLeftClose size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="app-body">
        <header className="app-top">
          <span className="product-label">
            <b>N</b>
            <b>B</b>
            <b>G</b> <i /> CREDIT OPERATIONS
          </span>
          <div>
            <span className="local-indicator" />
            Τοπικός χώρος εργασίας
            <span className="top-divider" />
            <span className="synthetic-tag">SYNTHETIC DATA</span>
          </div>
        </header>
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/new" element={<NewCase />} />
          <Route path="/cases/:cid/:tab?" element={<CasePage />} />
          <Route
            path="*"
            element={
              <Empty title="Η σελίδα δεν βρέθηκε">
                <Link to="/">Επιστροφή στους φακέλους</Link>
              </Empty>
            }
          />
        </Routes>
      </div>
    </div>
  );
}

function Library() {
  const { data: cases = [], isLoading, error } = useCases();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const navigate = useNavigate();
  function openNewCase() {
    navigate("/new");
  }
  const pending = cases.filter((c) => c.summary?.draft).length,
    ready = cases.filter((c) => c.summary && !c.summary.draft).length;
  const visible = cases.filter(
    (c) =>
      c.name.toLocaleLowerCase("el").includes(search.toLocaleLowerCase("el")) &&
      (filter === "all" ||
        (filter === "ready" && c.summary && !c.summary.draft) ||
        (filter === "pending" && c.summary?.draft)),
  );
  if (isLoading) return <Loading />;
  return (
    <main className="library page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            ΤΑ ΕΓΓΡΑΦΑ ΓΙΝΟΝΤΑΙ ΤΕΚΜΗΡΙΩΜΕΝΑ ΣΤΟΙΧΕΙΑ
          </span>
          <h1>Κάθε φάκελος. Μια καθαρή εικόνα.</h1>
          <p>Όλα όσα χρειάζεστε για τον επόμενο έλεγχο, σε έναν χώρο.</p>
        </div>
        <Link to="/new" className="button primary">
          <Plus size={18} />
          Νέος φάκελος
        </Link>
      </div>
      <div className="library-hero">
        <div className="hero-content">
          <div className="hero-eyebrow">
            <span /> CREDITFILE STUDIO
          </div>
          <h2>
            Από την πληροφορία,
            <br />
            στην τεκμηρίωση.
          </h2>
          <p>
            Ελέγξτε τα στοιχεία. Ακολουθήστε τις πηγές.
            <br />
            Προετοιμάστε το επόμενο βήμα με σαφήνεια.
          </p>
          {cases[0] ? (
            <Link
              className="button hero-button"
              to={"/cases/" + cases[0].id + "/overview"}
            >
              Συνέχεια πρόσφατου φακέλου
              <ArrowRight size={17} />
            </Link>
          ) : (
            <button className="button hero-button" onClick={openNewCase}>
              <Sparkles size={17} />
              Δημιουργία πρώτου φακέλου
            </button>
          )}
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="document-sculpture back">
            <i />
            <i />
            <i />
          </div>
          <div className="document-sculpture front">
            <div className="sculpture-heading">
              <FileText size={24} />
              <span>
                ΕΠΑΛΗΘΕΥΣΗ
                <br />
                ΣΤΟΙΧΕΙΩΝ
              </span>
            </div>
            <i />
            <i />
            <div className="sculpture-value">
              Στοιχείο <ArrowRight size={16} /> Πηγή
            </div>
            <i />
            <i />
            <div className="sculpture-bottom">
              <ShieldCheck size={20} /> Με τεκμηρίωση
            </div>
          </div>
          <div className="floating-proof">
            <Check size={16} /> Συνδεδεμένη πηγή
          </div>
        </div>
      </div>
      <div className="stats-strip">
        <div>
          <span>Σύνολο φακέλων</span>
          <strong>{cases.length.toString().padStart(2, "0")}</strong>
          <FolderOpen />
        </div>
        <div>
          <span>Χρειάζονται έλεγχο</span>
          <strong>{pending.toString().padStart(2, "0")}</strong>
          <Clock3 />
        </div>
        <div>
          <span>Έτοιμοι για δελτίο</span>
          <strong>{ready.toString().padStart(2, "0")}</strong>
          <FileCheck2 />
        </div>
      </div>
      <div className="section-heading">
        <div>
          <h2>
            Οι φάκελοί μου <span className="count">{cases.length}</span>
          </h2>
          <p>Ελέγξτε τα στοιχεία των φακέλων σας, με πλήρες ιστορικό.</p>
        </div>
      </div>
      <div className="library-toolbar">
        <div className="segmented">
          {[
            ["all", "Όλοι"],
            ["pending", "Προς έλεγχο"],
            ["ready", "Έτοιμοι"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={filter === key ? "active" : ""}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="search">
          <Search size={17} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Αναζήτηση επωνυμίας…"
            aria-label="Αναζήτηση φακέλων"
          />
        </label>
      </div>
      {error && <ErrorBox error={error} />}
      <div className="case-table">
        <div className="case-table-head">
          <span>ΕΠΙΧΕΙΡΗΣΗ / ΦΑΚΕΛΟΣ</span>
          <span>ΚΑΤΑΣΤΑΣΗ</span>
          <span>ΔΕΛΤΙΟ</span>
          <span>ΔΗΜΙΟΥΡΓΗΘΗΚΕ</span>
          <span />
        </div>
        {visible.map((c) => (
          <Link
            className="case-row"
            to={"/cases/" + c.id + "/overview"}
            key={c.id}
          >
            <div className="company-cell">
              <span className="company-avatar">
                {c.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <strong>{c.name}</strong>
                <small>Φάκελος {c.id.slice(0, 8).toUpperCase()}</small>
              </div>
            </div>
            <div>
              <Badge
                tone={
                  !c.summary ? "neutral" : c.summary.draft ? "amber" : "green"
                }
              >
                {!c.summary
                  ? "Αναμονή ανάλυσης"
                  : c.summary.draft
                    ? c.summary.state === "Εκκρεμούν στοιχεία ή διευκρινίσεις"
                      ? "Αναμονή διευκρινίσεων"
                      : "Προς έλεγχο"
                    : "Έτοιμος για δελτίο"}
              </Badge>
            </div>
            <div className="table-progress">
              <span>
                {c.summary?.reviewed ?? 0}
                <small> / 10</small>
              </span>
              <i>
                <b style={{ width: (c.summary?.reviewed ?? 0) * 10 + "%" }} />
              </i>
            </div>
            <small>{dateLabel(c.created)}</small>
            <ArrowUpRight size={18} />
          </Link>
        ))}
        {!visible.length && (
          <Empty
            title={
              cases.length
                ? "Δεν βρέθηκαν φάκελοι"
                : "Ο χώρος σας είναι έτοιμος"
            }
          >
            <p>
              {cases.length
                ? "Δοκιμάστε διαφορετική αναζήτηση ή φίλτρο."
                : "Δημιουργήστε έναν φάκελο από τα έγγραφά σας."}
            </p>
          </Empty>
        )}
      </div>
      <footer className="workspace-footer">
        <ShieldCheck size={14} />
        Οι επιβεβαιώσεις σας αποθηκεύονται αποκλειστικά στο Studio.
        <span>Η προετοιμασία δελτίου δεν αποτελεί πιστωτική απόφαση.</span>
      </footer>
    </main>
  );
}

function NewCase() {
  const [files, setFiles] = useState<File[]>([]),
    [kinds, setKinds] = useState<Record<string, string>>({}),
    [synthetic, setSynthetic] = useState(false),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null),
    folder = useRef<HTMLInputElement>(null);
  const qc = useQueryClient(),
    navigate = useNavigate();
  async function choose(incoming: File[]) {
    const pdfs = incoming.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    setFiles(pdfs);
    setKinds({});
    setErr("");
    setBusy(true);
    try {
      const fd = new FormData();
      pdfs.forEach((f) => fd.append("files", f));
      const r = await post("/discover", fd);
      setKinds(
        Object.fromEntries(r.files.map((f: any) => [f.id, f.kind || ""])),
      );
      setWarnings(r.warnings);
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const apps = files.filter((_, i) => kinds[i] === "application"),
        fins = files.filter((_, i) => kinds[i] === "financials");
      if (apps.length !== 1 || fins.length !== 1)
        throw new Error(
          "Επιλέξτε ακριβώς μία αίτηση και μία οικονομική κατάσταση.",
        );
      const fd = new FormData();
      fd.append("synthetic", String(synthetic));
      fd.append("application", apps[0]);
      fd.append("financials", fins[0]);
      const c = await post("/cases", fd);
      await qc.invalidateQueries({ queryKey: ["cases"] });
      navigate("/cases/" + c.id + "/documents");
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="new-case library page-enter">
      <Link to="/" className="back-link">
        <ArrowLeft size={16} />
        Οι φάκελοί μου
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ΝΕΑ ΕΡΓΑΣΙΑ</span>
          <h1>Ξεκινήστε από τα έγγραφα.</h1>
          <p>
            Προσθέστε μία αίτηση χρηματοδότησης και τις οικονομικές καταστάσεις.
          </p>
        </div>
        <span className="step-marker">
          01 <i /> ΕΙΣΑΓΩΓΗ
        </span>
      </div>
      <div className="upload-layout">
        <form className="panel upload-panel" onSubmit={submit}>
          <div
            className="dropzone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (!busy) void choose(Array.from(e.dataTransfer.files));
            }}
          >
            <div className="upload-icon">
              <Upload size={27} />
            </div>
            <h2>Σύρετε εδώ τα PDF σας</h2>
            <p>Έως 10 MB και 10 σελίδες ανά PDF · Αναγνώσιμο κείμενο</p>
            <div className="button-row">
              <button
                type="button"
                className="button primary"
                disabled={busy}
                onClick={() => input.current?.click()}
              >
                <Plus size={16} />
                Επιλογή PDF
              </button>
              <button
                type="button"
                className="button secondary"
                disabled={busy}
                onClick={() => folder.current?.click()}
              >
                Επιλογή φακέλου
              </button>
            </div>
            <input
              ref={input}
              type="file"
              accept="application/pdf"
              multiple
              hidden
              onChange={(e) => void choose(Array.from(e.target.files || []))}
            />
            <input
              ref={folder}
              type="file"
              multiple
              hidden
              {...({ webkitdirectory: "" } as any)}
              onChange={(e) => void choose(Array.from(e.target.files || []))}
            />
          </div>
          {busy && <p role="status">Έλεγχος εγγράφων…</p>}
          {files.map((f, i) => (
            <div className="upload-file" key={i}>
              <FileText size={22} />
              <div>
                <b>{f.name}</b>
                <small>{(f.size / 1024 / 1024).toFixed(2)} MB</small>
              </div>
              <select
                aria-label={"Τύπος " + f.name}
                value={kinds[i] || ""}
                onChange={(e) => setKinds({ ...kinds, [i]: e.target.value })}
              >
                <option value="">Εκτός επιλογής</option>
                <option value="application">Αίτηση</option>
                <option value="financials">Οικονομικές καταστάσεις</option>
              </select>
            </div>
          ))}
          {warnings.map((w, i) => (
            <p className="muted" key={i}>
              {w}
            </p>
          ))}
          <p className="muted">
            Η επωνυμία συμπληρώνεται αυτόματα από τα έγγραφα.
          </p>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={synthetic}
              onChange={(e) => setSynthetic(e.target.checked)}
              required
            />
            Τα έγγραφα περιέχουν αποκλειστικά συνθετικά δεδομένα.
          </label>
          {err && <ErrorBox error={new Error(err)} />}
          <div className="form-bottom">
            <span>Η ανάλυση ξεκινά με ξεχωριστή ενέργεια.</span>
            <button
              className="button primary"
              disabled={busy || !files.length || !synthetic}
            >
              Δημιουργία φακέλου
              <ArrowRight size={17} />
            </button>
          </div>
        </form>
        <aside className="import-guide">
          <span className="eyebrow">ΜΙΑ ΚΑΘΑΡΗ ΔΙΑΔΡΟΜΗ</span>
          <h2>
            Τα σωστά έγγραφα.
            <br />
            Στον σωστό φάκελο.
          </h2>
          {[
            [
              "01",
              "Επιλέξτε έγγραφα",
              "Ο τύπος αναγνωρίζεται τοπικά. Αν υπάρχουν πολλές εκδόσεις, επιλέγετε τη σωστή.",
            ],
            [
              "02",
              "Επιβεβαιώστε τον φάκελο",
              "Ελέγξτε τα αρχεία πριν ξεκινήσετε. Η επωνυμία αναγνωρίζεται αυτόματα.",
            ],
            [
              "03",
              "Προχωρήστε στην ανάλυση",
              "Η AI προτείνει στοιχεία με πηγές. Εσείς ολοκληρώνετε τον έλεγχο.",
            ],
          ].map(([n, t, d]) => (
            <div className="guide-step" key={n}>
              <span>{n}</span>
              <div>
                <h3>{t}</h3>
                <p>{d}</p>
              </div>
            </div>
          ))}
        </aside>
      </div>
    </main>
  );
}

function CasePage() {
  const { cid = "", tab = "overview" } = useParams();
  const [params, setParams] = useSearchParams();
  const {
    data: info,
    error: infoError,
    isLoading: infoLoading,
  } = useQuery<CaseRow>({
    queryKey: ["case", cid],
    queryFn: () => api("/cases/" + cid),
  });
  const rid = params.get("run") || info?.run_id;
  const q = useQuery<Workspace>({
    queryKey: ["workspace", cid, rid],
    queryFn: () => api(`/cases/${cid}/runs/${rid}`),
    enabled: !!rid,
  });
  const [assistant, setAssistant] = useState(false);
  const [chatSource, setChatSource] = useState<Source | null>(null);
  const [chatContext, setChatContext] = useState<FieldValue | null>(null);
  const [chatSession, setChatSession] = useState<{
    scope: string;
    sid: string | null;
  } | null>(null);
  const qc = useQueryClient();
  async function refresh() {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["workspace", cid] }),
      qc.invalidateQueries({ queryKey: ["case", cid] }),
      qc.invalidateQueries({ queryKey: ["cases"] }),
    ]);
  }
  useEffect(() => {
    setChatSource(null);
    setChatContext(null);
    setChatSession(null);
    setAssistant(false);
  }, [cid, rid]);
  if (infoLoading || (rid && q.isLoading)) return <Loading />;
  if (infoError || q.error)
    return (
      <main className="library">
        <ErrorBox error={infoError || q.error} />
        <button className="button secondary" onClick={refresh}>
          <RefreshCw size={16} />
          Ανανέωση
        </button>
      </main>
    );
  if (!info) return null;
  const data = q.data;
  const report = data?.report;
  return (
    <main className="case-page page-enter">
      <div className="breadcrumb">
        <Link to="/">Οι φάκελοί μου</Link>
        <span>/</span>
        <span>{info.name}</span>
        <span className="case-id">#{cid.slice(0, 8).toUpperCase()}</span>
      </div>
      <div className="case-heading">
        <div>
          <div className="case-title-line">
            <span className="company-avatar">
              {info.name.slice(0, 2).toUpperCase()}
            </span>
            <h1>{info.name}</h1>
          </div>
          <div className="case-subtitle">
            <Badge
              tone={report?.draft ? "amber" : report ? "green" : "neutral"}
            >
              {report?.state || "Έτοιμος για ανάλυση"}
            </Badge>
            {data?.mode === "fixture" && (
              <span className="fixture-label">
                ΣΥΝΘΕΤΙΚΟ ΠΑΡΑΔΕΙΓΜΑ · ΧΩΡΙΣ ΚΛΗΣΗ AI
              </span>
            )}
          </div>
        </div>
        <div className="case-heading-actions">
          {data && (
            <>
              <div className="readiness">
                <span>
                  ΕΛΕΓΧΟΣ ΔΕΛΤΙΟΥ{" "}
                  <b>
                    {report.reviewed_count}
                    <small> / 10</small>
                  </b>
                </span>
                <div>
                  {Array.from({ length: 10 }, (_, i) => (
                    <i
                      key={i}
                      className={i < report.reviewed_count ? "done" : ""}
                    />
                  ))}
                </div>
              </div>
              <button
                className={"button " + (assistant ? "primary" : "secondary")}
                onClick={() => {
                  setAssistant(!assistant);
                  setChatSource(null);
                }}
              >
                <Sparkles size={17} />
                Βοηθός φακέλου
              </button>
            </>
          )}
        </div>
      </div>
      <div className="case-navigation">
        <nav>
          {Object.entries(titleMap).map(([key, label]) => {
            const Icon = icons[key as keyof typeof icons];
            return (
              <NavLink
                key={key}
                to={`/cases/${cid}/${key}${rid ? "?run=" + rid : ""}`}
              >
                <Icon size={17} />
                {label}
                {key === "review" && report?.pending_count > 0 && (
                  <span>{report.pending_count}</span>
                )}
              </NavLink>
            );
          })}
        </nav>
        {data && data.runs.length > 1 && (
          <label className="run-select">
            <History size={14} />
            <select
              aria-label="Έκδοση ανάλυσης"
              value={rid ?? ""}
              onChange={(e) => setParams({ run: e.target.value })}
            >
              {data.runs.map((r, i) => (
                <option key={r.id} value={r.id}>
                  {i === 0 ? "Τρέχουσα · " : ""}
                  {dateLabel(r.created)} · {r.id.slice(0, 5)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {report?.documents.some((d: any) => d.requires_reanalysis) && (
        <div className="notice amber">
          <CircleAlert size={18} />
          <span>
            Αντικαταστάθηκε έγγραφο. Τα στοιχεία ανήκουν στην προηγούμενη
            ανάλυση.
          </span>
          <Link to={`/cases/${cid}/documents`}>
            Νέα ανάλυση
            <ArrowRight size={15} />
          </Link>
        </div>
      )}
      {data?.errors?.map((e, i) => (
        <ErrorBox key={i} error={new Error(String(e))} />
      ))}
      <div className={"case-content " + (assistant ? "with-assistant" : "")}>
        <div className="case-main">
          {!data ? (
            <Documents cid={cid} refresh={refresh} />
          ) : tab === "review" ? (
            <ReviewDesk
              data={data}
              refresh={refresh}
              onAsk={(field) => {
                setChatContext(field);
                setAssistant(true);
              }}
            />
          ) : tab === "documents" ? (
            <Documents cid={cid} data={data} refresh={refresh} />
          ) : tab === "bulletin" ? (
            <Bulletin data={data} refresh={refresh} />
          ) : (
            <Overview data={data} />
          )}
        </div>
        {assistant && data && (
          <Chat
            key={cid + rid}
            data={data}
            context={chatContext}
            sid={chatSession?.scope === cid + rid ? chatSession.sid : null}
            setSid={(sid) => setChatSession({ scope: cid + rid, sid })}
            onSource={setChatSource}
            onClose={() => setAssistant(false)}
          />
        )}
      </div>
      {chatSource && data && (
        <Modal title="Η πηγή της απάντησης" onClose={() => setChatSource(null)}>
          <div className="source-modal">
            <PdfReader
              url={`${BASE}/cases/${cid}/documents/${data.report.documents.find((d: any) => d.id === chatSource.document_id)?.type || "financials"}?run=${rid}`}
              source={chatSource}
            />
          </div>
        </Modal>
      )}
    </main>
  );
}

function Overview({ data }: { data: Workspace }) {
  const { report, fields } = data,
    cid = data.case.id;
  const toReview = (field?: string) =>
    `/cases/${cid}/review?run=${data.run_id}${field ? "&field=" + field : ""}`;
  const amount = fields.find((f) => f.name === "requested_amount"),
    purpose = fields.find((f) => f.name === "financing_purpose"),
    tenor = fields.find((f) => f.name === "tenor_months");
  return (
    <div className="overview">
      <div className="overview-heading">
        <div>
          <span className="eyebrow">ΕΠΙΣΚΟΠΗΣΗ ΦΑΚΕΛΟΥ</span>
          <h2>Το επόμενο βήμα είναι ξεκάθαρο.</h2>
          <p>Ελέγξτε τις εκκρεμότητες και ακολουθήστε την τεκμηρίωση.</p>
        </div>
        <span className="overview-seal">
          <ShieldCheck size={28} />
        </span>
      </div>
      <div className="overview-grid">
        <section className="panel attention-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">01 / ΠΡΟΤΕΡΑΙΟΤΗΤΑ</span>
              <h3>Χρειάζονται την προσοχή σας</h3>
            </div>
            <span className="counter">{report.issues.length}</span>
          </div>
          {report.issues.length ? (
            report.issues.slice(0, 5).map((issue: any) => {
              const field = report.fields.find((f: any) => f.key === issue.id);
              return (
                <Link
                  key={issue.id}
                  to={
                    field
                      ? toReview(field.document_type + "." + field.field)
                      : toReview() + "&filter=conflicts"
                  }
                  className="attention-row"
                >
                  <span className="attention-icon">
                    <CircleAlert size={17} />
                  </span>
                  <div>
                    <b>{issue.label}</b>
                    <p>{issue.reason}</p>
                  </div>
                  <ArrowUpRight size={17} />
                </Link>
              );
            })
          ) : (
            <div className="completion">
              <CheckCheck size={36} />
              <h3>Ο έλεγχος ολοκληρώθηκε</h3>
              <p>Μπορείτε να προχωρήσετε στην έκδοση του δελτίου.</p>
            </div>
          )}
          <Link to={toReview()} className="button primary">
            {report.issues.length ? "Συνέχεια ελέγχου" : "Επισκόπηση στοιχείων"}
            <ArrowRight size={17} />
          </Link>
        </section>
        <section className="request-panel">
          <span className="eyebrow">02 / ΑΙΤΗΜΑ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ</span>
          <h3>Η εικόνα του αιτήματος</h3>
          <span className="amount-label">ΑΙΤΟΥΜΕΝΟ ΠΟΣΟ</span>
          <Link to={toReview(amount?.id)} className="request-amount">
            {valueLabel(amount?.normalized_value, true)}
            <ArrowUpRight size={20} />
          </Link>
          <Badge
            tone={amount && !needsFieldReview(amount) ? "green" : "neutral"}
          >
            {amount?.review_status === "corrected" && !amount.sources.length
              ? "Αποθηκευμένο · εκκρεμεί πηγή"
              : amount?.approved_for_credit_memo
                ? "Ελεγμένο στοιχείο"
                : "Πρόταση προς έλεγχο"}
          </Badge>
          <div className="request-detail">
            <small>Σκοπός χρηματοδότησης</small>
            <p>{valueLabel(purpose?.normalized_value)}</p>
          </div>
          <div className="request-detail">
            <small>Διάρκεια χρηματοδότησης</small>
            <strong>
              {valueLabel(tenor?.normalized_value)} <small>μήνες</small>
            </strong>
          </div>
          <div className="request-footer">
            <FileText size={17} />
            Κάθε στοιχείο συνδέεται με την πηγή του.
          </div>
        </section>
      </div>
      <div className="overview-documents">
        {report.documents.map((d: any) => (
          <Link to={`/cases/${cid}/documents?run=${data.run_id}`} key={d.id}>
            <span className="pdf-glyph">PDF</span>
            <div>
              <strong>{kindLabel(d.type)}</strong>
              <small>
                {d.name} · {d.page_count} σελίδες
              </small>
            </div>
            <ArrowUpRight size={18} />
          </Link>
        ))}
      </div>
    </div>
  );
}

function needsFieldReview(field: FieldValue) {
  return !field.approved_for_credit_memo || !field.sources.length;
}

function ReviewDesk({
  data,
  refresh,
  onAsk,
}: {
  data: Workspace;
  refresh: () => Promise<void>;
  onAsk: (field: FieldValue) => void;
}) {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const filter = params.get("filter") || "all";
  const selected =
    data.fields.find((f) => f.id === params.get("field")) ||
    data.fields.find(needsFieldReview) ||
    data.fields[0];
  const [source, setSource] = useState<Source | null>(null),
    [edit, setEdit] = useState<"corrected" | "unresolved" | null>(null),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState(""),
    [saved, setSaved] = useState(""),
    [checked, setChecked] = useState<string[]>([]),
    [bulkConfirm, setBulkConfirm] = useState(false),
    [history, setHistory] = useState(false);
  useEffect(() => {
    setEdit(null);
    setErr("");
    setSaved("");
  }, [selected?.id, data.run_id]);
  useEffect(() => {
    setSource(selected?.sources[0] || null);
  }, [selected?.id, data.run_id, data.report.fingerprint]);
  const base = `/cases/${data.case.id}/runs/${data.run_id}`;
  const setSelection = (id: string) => {
    setParams((p) => {
      p.set("field", id);
      return p;
    });
  };
  async function accept() {
    setBusy(true);
    setErr("");
    try {
      await post(base + "/review", {
        ...command(data.report.fingerprint),
        kind: selected.kind,
        field: selected.name,
        decision: "accepted",
      });
      setSelection(selected.id);
      await refresh();
      setSaved("Η επιβεβαίωση αποθηκεύτηκε.");
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function bulk() {
    setBusy(true);
    setErr("");
    try {
      await post(base + "/bulk", {
        ...command(data.report.fingerprint),
        selected: checked.map((id) => id.split(".")),
      });
      setChecked([]);
      setBulkConfirm(false);
      await refresh();
      setSaved("Τα επιλεγμένα στοιχεία επιβεβαιώθηκαν.");
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  const visible = data.fields.filter(
    (f) =>
      f.label.toLowerCase().includes(search.toLowerCase()) &&
      (filter !== "pending" || needsFieldReview(f)),
  );
  useEffect(() => {
    setChecked((ids) =>
      ids.filter((id) => visible.some((f) => f.id === id && f.eligible)),
    );
  }, [data.report.fingerprint, filter, search]);
  if (filter === "conflicts")
    return (
      <ConflictDesk
        data={data}
        refresh={refresh}
        onBack={() =>
          setParams((p) => {
            p.delete("filter");
            return p;
          })
        }
      />
    );
  return (
    <>
      <div className="review-heading">
        <div>
          <h2>Στοιχεία & τεκμηρίωση</h2>
          <p>Επιλέξτε ένα στοιχείο για να δείτε ακριβώς από πού προέρχεται.</p>
        </div>
        <button
          className="button secondary"
          onClick={() =>
            setParams((p) => {
              p.set("filter", "conflicts");
              return p;
            })
          }
        >
          <Layers3 size={16} />
          Ασυμφωνίες{" "}
          <span className="count">
            {data.report.conflicts.filter((c: any) => !c.resolution).length}
          </span>
        </button>
      </div>
      <div className="review-layout">
        <section className="panel field-list">
          <div className="field-toolbar">
            <div className="segmented">
              <button
                className={filter === "all" ? "active" : ""}
                onClick={() =>
                  setParams((p) => {
                    p.delete("filter");
                    return p;
                  })
                }
              >
                Όλα <span>{data.fields.length}</span>
              </button>
              <button
                className={filter === "pending" ? "active" : ""}
                onClick={() =>
                  setParams((p) => {
                    p.set("filter", "pending");
                    return p;
                  })
                }
              >
                Εκκρεμή
              </button>
            </div>
            <label className="search">
              <Search size={15} />
              <input
                placeholder="Αναζήτηση στοιχείου…"
                aria-label="Αναζήτηση στοιχείου"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
          </div>
          {checked.length > 0 && (
            <div className="bulk-bar">
              <span>{checked.length} επιλεγμένα</span>
              <button disabled={busy} onClick={() => setBulkConfirm(true)}>
                Επιβεβαίωση όλων ({checked.length})
              </button>
              <button
                onClick={() => setChecked([])}
                aria-label="Καθαρισμός επιλογής"
              >
                <X size={15} />
              </button>
            </div>
          )}
          <div className="field-scroll">
            {["application", "financials"].map((kind) => (
              <div key={kind}>
                <div className="field-group-title">
                  <FileText size={13} />
                  {kindLabel(kind)}
                </div>
                {visible
                  .filter((f) => f.kind === kind)
                  .map((f) => (
                    <div
                      className={
                        "field-row " + (selected?.id === f.id ? "selected" : "")
                      }
                      key={f.id}
                    >
                      <input
                        type="checkbox"
                        aria-label={
                          "Επιλογή " + f.label + " " + kindLabel(kind)
                        }
                        disabled={!f.eligible}
                        checked={checked.includes(f.id)}
                        onChange={(e) =>
                          setChecked(
                            e.target.checked
                              ? [...checked, f.id]
                              : checked.filter((id) => id !== f.id),
                          )
                        }
                      />
                      <button onClick={() => setSelection(f.id)}>
                        <span>
                          {f.label}
                          <small>
                            {f.review_status === "corrected" &&
                            !f.sources.length ? (
                              "Αποθηκευμένο · εκκρεμεί πηγή"
                            ) : f.approved_for_credit_memo ? (
                              <>
                                <Check size={11} />
                                {f.status === "manually_corrected"
                                  ? "Διορθωμένο · αποθηκεύτηκε"
                                  : "Ελεγμένο"}
                              </>
                            ) : f.normalized_value == null ? (
                              "Λείπει στοιχείο"
                            ) : f.status === "uncertain" ? (
                              "Χρειάζεται διευκρίνιση"
                            ) : (
                              "Προς έλεγχο"
                            )}
                          </small>
                        </span>
                        <strong className={f.money ? "numeric" : ""}>
                          {valueLabel(f.normalized_value, f.money)}
                        </strong>
                      </button>
                      <ArrowUpRight size={13} />
                    </div>
                  ))}
              </div>
            ))}
          </div>
        </section>
        <section className="review-focus">
          <div className="selected-card">
            <div className="selected-heading">
              <div>
                <span className="eyebrow">{kindLabel(selected.kind)}</span>
                <h3>{selected.label}</h3>
              </div>
              <Badge tone={needsFieldReview(selected) ? "amber" : "green"}>
                {selected.review_status === "corrected" &&
                !selected.sources.length
                  ? "Εκκρεμεί πηγή"
                  : selected.approved_for_credit_memo
                    ? "Ελεγμένο"
                    : "Προς έλεγχο"}
              </Badge>
            </div>
            <div
              className={"selected-value " + (selected.money ? "numeric" : "")}
            >
              {valueLabel(selected.normalized_value, selected.money)}
            </div>
            {(selected.review_reason || selected.uncertainty) && (
              <p className="field-note">
                {selected.review_reason || selected.uncertainty}
              </p>
            )}
            <div className="source-pills">
              {selected.sources.map((s, i) => (
                <button
                  key={i}
                  className={source === s ? "active" : ""}
                  onClick={() => setSource(s)}
                >
                  <FileText size={13} />
                  Σελ. {s.page}
                  <ArrowUpRight size={12} />
                </button>
              ))}
              {!selected.sources.length && (
                <small className="muted">Δεν υπάρχει επαληθευμένη πηγή.</small>
              )}
            </div>
            <div className="review-actions">
              <button
                className="button primary"
                onClick={() =>
                  checked.length ? setBulkConfirm(true) : void accept()
                }
                disabled={
                  busy ||
                  (!checked.length &&
                    (selected.status !== "extracted" ||
                      !!selected.approved_for_credit_memo))
                }
              >
                <Check size={16} />
                {checked.length
                  ? `Επιβεβαίωση όλων (${checked.length})`
                  : "Επιβεβαίωση πεδίου"}
              </button>
              <button
                className="button secondary"
                onClick={() => {
                  setSaved("");
                  setEdit("corrected");
                }}
              >
                <Pencil size={15} />
                Διόρθωση
              </button>
              <button
                className="icon-button"
                title="Χρειάζεται διευκρίνιση"
                aria-label="Σήμανση ως ανεπίλυτο"
                onClick={() => {
                  setSaved("");
                  setEdit("unresolved");
                }}
              >
                <CircleAlert size={18} />
              </button>
              <button
                className="icon-button"
                title="Ρώτησε για αυτό"
                aria-label="Ρώτησε για αυτό"
                onClick={() => onAsk(selected)}
              >
                <Sparkles size={18} />
              </button>
            </div>
            {err && <ErrorBox error={new Error(err)} />}
            <button
              className="button text history-button"
              onClick={() => setHistory(true)}
            >
              <History size={13} />
              Ιστορικό στοιχείου
            </button>
            <div className="save-status" role="status">
              {saved && (
                <>
                  <CheckCheck size={14} />
                  {saved}
                  <button
                    onClick={() => {
                      const next = data.fields.find(
                        (f) => f.id !== selected.id && needsFieldReview(f),
                      );
                      if (next) {
                        setSelection(next.id);
                        setSaved("");
                      }
                    }}
                  >
                    Επόμενο
                    <ArrowRight size={13} />
                  </button>
                </>
              )}
            </div>
          </div>
          <PdfReader
            url={`${BASE}/cases/${data.case.id}/documents/${selected.kind}?run=${data.run_id}`}
            source={source}
            title={kindLabel(selected.kind)}
          />
        </section>
      </div>
      {history && (
        <Modal
          title={`Ιστορικό · ${selected.label}`}
          onClose={() => setHistory(false)}
        >
          <div className="review-history">
            {data.reviews
              .filter(
                (e) =>
                  e.document_type === selected.kind &&
                  e.field === selected.name,
              )
              .map((e, i) => (
                <article key={i}>
                  <small>{new Date(e.timestamp).toLocaleString("el-GR")}</small>
                  <h3>
                    {e.review_decision === "accepted"
                      ? "Επιβεβαίωση"
                      : e.review_decision === "corrected"
                        ? "Διόρθωση"
                        : "Ανεπίλυτο"}
                  </h3>
                  <p>
                    {valueLabel(
                      e.corrected_value ?? e.reviewed_value,
                      selected.money,
                    )}
                  </p>
                  <p className="muted">{e.reviewer_comment}</p>
                </article>
              ))}
            {!data.reviews.some(
              (e) =>
                e.document_type === selected.kind && e.field === selected.name,
            ) && (
              <p className="muted">
                Δεν έχει καταγραφεί απόφαση για αυτό το στοιχείο.
              </p>
            )}
          </div>
        </Modal>
      )}
      {edit && (
        <EditField
          data={data}
          field={selected}
          decision={edit}
          onClose={() => setEdit(null)}
          onSaved={async (feedback) => {
            setSelection(selected.id);
            await refresh();
            setEdit(null);
            setSaved(feedback);
          }}
        />
      )}
      {bulkConfirm && (
        <Modal
          title="Επιβεβαίωση επιλεγμένων στοιχείων"
          onClose={() => setBulkConfirm(false)}
        >
          <p>
            Επιβεβαιώνετε ότι ελέγξατε τις τιμές και τις πηγές των{" "}
            {checked.length} επιλεγμένων στοιχείων;
          </p>
          <ul>
            {data.fields
              .filter((f) => checked.includes(f.id))
              .map((f) => (
                <li key={f.id}>
                  {f.label} · {kindLabel(f.kind)}
                </li>
              ))}
          </ul>
          <p className="muted">
            Οι συγκρίσεις ενημερώνονται με τις τρέχουσες τιμές. Όσες
            εξακολουθούν να διαφέρουν χρειάζονται καταγραφή επίλυσης.
          </p>
          {err && <ErrorBox error={new Error(err)} />}
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setBulkConfirm(false)}
            >
              Επιστροφή
            </button>
            <button className="button primary" disabled={busy} onClick={bulk}>
              Επιβεβαίωση {checked.length} στοιχείων
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

function EditField({
  data,
  field,
  decision,
  onClose,
  onSaved,
}: {
  data: Workspace;
  field: FieldValue;
  decision: string;
  onClose: () => void;
  onSaved: (feedback: string) => Promise<void>;
}) {
  const [value, setValue] = useState(String(field.normalized_value ?? "")),
    [reason, setReason] = useState(""),
    [source, setSource] = useState(
      field.review_status === "corrected" && field.sources.length ? "0" : "",
    ),
    [expected] = useState(data.report.fingerprint),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  const { data: pageBlocks = [] } = useQuery<Source[]>({
    queryKey: ["blocks", data.case.id, data.run_id, field.kind],
    queryFn: () =>
      api(
        `/cases/${data.case.id}/runs/${data.run_id}/blocks?kind=${field.kind}`,
      ),
    enabled: decision === "corrected",
  });
  const blocks = [...field.sources, ...pageBlocks];
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await post(`/cases/${data.case.id}/runs/${data.run_id}/review`, {
        ...command(expected),
        kind: field.kind,
        field: field.name,
        decision,
        comment: reason,
        corrected:
          decision === "corrected"
            ? field.money
              ? canonicalMoney(value)
              : value
            : null,
        sources: source ? [blocks[Number(source)]] : [],
      });
      await onSaved(
        decision === "corrected"
          ? `${field.label}: ${valueLabel(field.money ? canonicalMoney(value) : value, field.money)} — αποθηκεύτηκε.${source ? "" : " Εκκρεμεί επιλογή πηγής."}`
          : "Η διευκρίνιση αποθηκεύτηκε.",
      );
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={
        (decision === "corrected" ? "Διόρθωση · " : "Διευκρίνιση · ") +
        field.label
      }
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={save}>
        {decision === "corrected" && (
          <>
            <label className="form-label">
              Νέα τιμή {field.money ? "σε EUR" : ""}
              <input
                required
                disabled={busy}
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </label>
            <label className="form-label">
              Τεκμηρίωση από το έγγραφο
              <select
                disabled={busy}
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="">Χειροκίνητη τιμή χωρίς τεκμηρίωση</option>
                {blocks.map((b, i) => (
                  <option value={i} key={i}>
                    Σελ. {b.page} · {b.quote.slice(0, 120)}
                  </option>
                ))}
              </select>
            </label>
            {source && (
              <blockquote className="block-preview">
                {blocks[Number(source)]?.quote}
              </blockquote>
            )}
            {!source && (
              <p className="muted">
                Η τιμή αποθηκεύεται. Το στοιχείο παραμένει εκκρεμές μέχρι να
                επιλέξετε πηγή που τεκμηριώνει τη διόρθωση.
              </p>
            )}
          </>
        )}
        <label className="form-label">
          Αιτιολογία
          <textarea
            required
            disabled={busy}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Καταγράψτε τη βάση της απόφασής σας…"
          />
        </label>
        {err && <ErrorBox error={new Error(err)} />}
        <div className="modal-actions">
          <button
            type="button"
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            Επιστροφή
          </button>
          <button className="button primary" disabled={busy}>
            Αποθήκευση απόφασης
            <Check size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ConflictDesk({
  data,
  refresh,
  onBack,
}: {
  data: Workspace;
  refresh: () => Promise<void>;
  onBack: () => void;
}) {
  const [selected, setSelected] = useState(0),
    [reason, setReason] = useState(""),
    [err, setErr] = useState(""),
    [busy, setBusy] = useState(false);
  const conflicts = data.report.conflicts;
  const c = conflicts[selected];
  async function resolve(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await post(`/cases/${data.case.id}/runs/${data.run_id}/resolve`, {
        ...command(data.report.fingerprint),
        check_id: c.check_id,
        basis: c.basis,
        reason,
        sources: c.evidence,
      });
      await refresh();
      setReason("");
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="conflict-desk">
      <div className="review-heading">
        <div>
          <button className="back-link" onClick={onBack}>
            <ArrowLeft size={15} />
            Όλα τα στοιχεία
          </button>
          <h2>Αντιπαραβολή πηγών</h2>
        </div>
        <Badge tone="amber">
          {conflicts.filter((x: any) => !x.resolution).length} εκκρεμείς έλεγχοι
        </Badge>
      </div>
      {!c ? (
        <Empty title="Δεν υπάρχουν ανοικτές ασυμφωνίες">
          <p>Ο έλεγχος κάθε στοιχείου παραμένει διαθέσιμος.</p>
        </Empty>
      ) : (
        <>
          <div className="conflict-tabs">
            {conflicts.map((x: any, i: number) => (
              <button
                className={i === selected ? "active" : ""}
                key={x.check_id}
                disabled={busy}
                onClick={() => {
                  setSelected(i);
                  setReason("");
                  setErr("");
                }}
              >
                {x.resolution ? <Check size={14} /> : <CircleAlert size={14} />}{" "}
                {x.label}
              </button>
            ))}
          </div>
          <div className="panel comparison-summary">
            <div>
              <span className="eyebrow">ΣΥΓΚΡΙΣΗ ΣΤΟΙΧΕΙΩΝ</span>
              <h3>{c.label}</h3>
              <p>{c.explanation}</p>
            </div>
            <Badge
              tone={
                c.resolution
                  ? "green"
                  : c.status === "NOT_CHECKED"
                    ? "neutral"
                    : "amber"
              }
            >
              {c.resolution
                ? "Επιλύθηκε"
                : c.status === "NOT_CHECKED"
                  ? "Ανεπαρκή στοιχεία"
                  : "Χρειάζεται επίλυση"}
            </Badge>
            <div className="comparison-values">
              <div>
                <small>
                  {c.check_id === "accounting_equation"
                    ? "Σύνολο ενεργητικού"
                    : "Αίτηση χρηματοδότησης"}
                </small>
                <strong>
                  {valueLabel(
                    c.left_value,
                    [
                      "turnover_match",
                      "debt_match",
                      "accounting_equation",
                    ].includes(c.check_id),
                  )}
                </strong>
              </div>
              <div>
                <small>
                  {c.check_id === "accounting_equation"
                    ? "Υποχρεώσεις + ίδια κεφάλαια"
                    : "Οικονομικές καταστάσεις"}
                </small>
                <strong>
                  {valueLabel(
                    c.right_value,
                    [
                      "turnover_match",
                      "debt_match",
                      "accounting_equation",
                    ].includes(c.check_id),
                  )}
                </strong>
              </div>
              {c.absolute_difference != null && (
                <div className="comparison-difference">
                  <small>Απόλυτη διαφορά</small>
                  <strong>
                    {valueLabel(
                      c.absolute_difference,
                      [
                        "turnover_match",
                        "debt_match",
                        "accounting_equation",
                      ].includes(c.check_id),
                    )}
                  </strong>
                  {c.percentage_difference != null && (
                    <small>
                      {new Intl.NumberFormat("el-GR", {
                        maximumFractionDigits: 2,
                      }).format(c.percentage_difference)}
                      %
                    </small>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="comparison-readers">
            {["application", "financials"].map((kind) => {
              const doc = data.report.documents.find(
                (d: any) => d.type === kind,
              );
              const source = c.evidence?.find(
                (s: Source) => s.document_id === doc.id,
              );
              return (
                <PdfReader
                  key={kind}
                  url={`${BASE}/cases/${data.case.id}/documents/${kind}?run=${data.run_id}`}
                  source={source}
                  title={kindLabel(kind)}
                />
              );
            })}
          </div>
          {c.resolution ? (
            <div className="notice green">
              <CheckCheck size={18} />
              {c.resolution.reason}
            </div>
          ) : c.status === "NOT_CHECKED" ? (
            <div className="notice amber">
              Συμπληρώστε πρώτα τα στοιχεία που χρειάζονται για τη σύγκριση.
            </div>
          ) : (
            <form className="panel resolution-form" onSubmit={resolve}>
              <label className="form-label">
                Καταγραφή επίλυσης
                <textarea
                  required
                  value={reason}
                  disabled={busy}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Αιτιολογήστε την επίλυση με βάση τις δύο πηγές…"
                />
              </label>
              <p className="muted">
                Οι τεκμηριωμένες παραπομπές της σύγκρισης αποθηκεύονται με την
                απόφαση.
              </p>
              {err && <ErrorBox error={new Error(err)} />}
              <button
                className="button primary"
                disabled={busy || !c.evidence?.length}
              >
                <Check size={16} />
                Αποθήκευση επίλυσης
              </button>
            </form>
          )}
        </>
      )}
    </div>
  );
}

function Documents({
  cid,
  data,
  refresh,
}: {
  cid: string;
  data?: Workspace;
  refresh: () => Promise<void>;
}) {
  const [kind, setKind] = useState("application"),
    [confirm, setConfirm] = useState(false),
    [replacement, setReplacement] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  const qc = useQueryClient();
  const { data: jobs = [] } = useQuery<any[]>({
    queryKey: ["jobs", cid],
    queryFn: () => api(`/cases/${cid}/jobs`),
    refetchInterval: (q) =>
      q.state.data?.some((j) => ["queued", "running"].includes(j.state))
        ? 1200
        : false,
  });
  const job = jobs[0];
  const active = job && ["queued", "running"].includes(job.state);
  const lastJob = useRef("");
  useEffect(() => {
    if (
      job?.run_id &&
      !["queued", "running"].includes(job.state) &&
      lastJob.current !== job.id
    ) {
      lastJob.current = job.id;
      void refresh();
    }
  }, [job?.state, job?.id, job?.run_id]);
  async function analyze() {
    setBusy(true);
    setErr("");
    try {
      await post(`/cases/${cid}/analyses`);
      setConfirm(false);
      await qc.invalidateQueries({ queryKey: ["jobs", cid] });
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="documents">
      <div className="review-heading">
        <div>
          <h2>Τα έγγραφα του φακέλου</h2>
          <p>Η σωστή έκδοση, με πλήρη διαδρομή τεκμηρίωσης.</p>
        </div>
        <button
          className="button primary"
          disabled={busy || active || data?.execution_mode === "replay"}
          onClick={() => setConfirm(true)}
        >
          <Sparkles size={17} />
          Έναρξη ανάλυσης
        </button>
      </div>
      {err && <ErrorBox error={new Error(err)} />}
      <div className="document-cards">
        {["application", "financials"].map((k) => (
          <button
            className={"document-card " + (kind === k ? "active" : "")}
            key={k}
            onClick={() => setKind(k)}
          >
            <span className="pdf-glyph large">PDF</span>
            <div>
              <span className="eyebrow">
                {k === "application" ? "01 / ΑΙΤΗΣΗ" : "02 / ΟΙΚΟΝΟΜΙΚΑ"}
              </span>
              <h3>{kindLabel(k)}</h3>
              <p>
                {data?.report.documents.find((d: any) => d.type === k)?.name ||
                  "Αποθηκευμένο PDF"}
              </p>
            </div>
            <ArrowUpRight size={20} />
          </button>
        ))}
      </div>
      {job && (
        <div
          className={
            "analysis-job " +
            (job.state === "failed" || job.state === "interrupted"
              ? "failed"
              : "")
          }
          role="status"
        >
          <div>
            {active ? (
              <LoaderCircle className="spin" size={20} />
            ) : job.state === "complete" ? (
              <CheckCheck size={20} />
            ) : (
              <CircleAlert size={20} />
            )}
            <b>{job.detail}</b>
          </div>
          <AnalysisProgress job={job} />
          {job.run_id && (
            <Link
              className="button secondary"
              to={`/cases/${cid}/review?run=${job.run_id}`}
            >
              Άνοιγμα ανάλυσης
              <ArrowRight size={16} />
            </Link>
          )}
        </div>
      )}
      <div className="document-view-layout">
        <PdfReader
          url={`${BASE}/cases/${cid}/documents/${kind}${data ? "?run=" + data.run_id : ""}`}
          title={kindLabel(kind)}
        />
        <aside className="panel document-info">
          <span className="eyebrow">ΔΙΑΧΕΙΡΙΣΗ ΕΓΓΡΑΦΟΥ</span>
          <h3>Κρατήστε την εικόνα ενημερωμένη.</h3>
          <p>
            Αν έχετε νεότερο PDF, αντικαταστήστε το και εκτελέστε νέα ανάλυση.
          </p>
          <p className="muted">
            Οι προηγούμενες αναλύσεις και τα δελτία διατηρούν τις αρχικές πηγές
            τους.
          </p>
          <button
            className="button secondary"
            disabled={!data || active}
            onClick={() =>
              setReplacement(
                data?.report.documents.find((d: any) => d.type === kind),
              )
            }
          >
            <RefreshCw size={16} />
            Αντικατάσταση PDF
          </button>
          <div className="document-facts">
            <div>
              <span>Τύπος</span>
              <b>{kindLabel(kind)}</b>
            </div>
            <div>
              <span>Χώρος</span>
              <b>Numbers Become Guidance</b>
            </div>
            <div>
              <span>Δεδομένα</span>
              <b>Αποκλειστικά συνθετικά</b>
            </div>
          </div>
        </aside>
      </div>
      {confirm && (
        <Modal title="Έναρξη ανάλυσης" onClose={() => setConfirm(false)}>
          <p>
            Θα αναλυθούν τα δύο τρέχοντα PDF και θα δημιουργηθεί νέα ανάλυση με
            προτεινόμενα στοιχεία και πηγές.
          </p>
          <div className="notice amber">
            Η ενέργεια χρησιμοποιεί τον ρυθμισμένο πάροχο AI και μπορεί να
            χρεωθεί. Οι προτάσεις χρειάζονται ανθρώπινο έλεγχο.
          </div>
          {err && <ErrorBox error={new Error(err)} />}
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setConfirm(false)}
            >
              Επιστροφή
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={analyze}
            >
              Έναρξη
              <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
      {replacement && (
        <ReplaceDocument
          cid={cid}
          document={replacement}
          onClose={() => setReplacement(null)}
          onSaved={async () => {
            setReplacement(null);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function ReplaceDocument({
  cid,
  document: doc,
  onClose,
  onSaved,
}: {
  cid: string;
  document: any;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [file, setFile] = useState<File>(),
    [synthetic, setSynthetic] = useState(false),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setErr("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("synthetic", String(synthetic));
      fd.append("expected", doc.hash);
      await post(`/cases/${cid}/replace/${doc.type}`, fd);
      await onSaved();
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Αντικατάσταση PDF" onClose={onClose}>
      <form onSubmit={save}>
        <p>
          {kindLabel(doc.type)} · {doc.name}
        </p>
        <label className="form-label">
          Νέο PDF
          <input
            required
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0])}
          />
        </label>
        <label className="checkbox-line">
          <input
            required
            type="checkbox"
            checked={synthetic}
            onChange={(e) => setSynthetic(e.target.checked)}
          />
          Περιέχει αποκλειστικά συνθετικά δεδομένα.
        </label>
        <p className="muted">
          Θα απαιτηθεί νέα ανάλυση και επαλήθευση των επηρεαζόμενων στοιχείων.
        </p>
        {err && <ErrorBox error={new Error(err)} />}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Επιστροφή
          </button>
          <button
            className="button primary"
            disabled={busy || !file || !synthetic}
          >
            Αντικατάσταση
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Bulletin({
  data,
  refresh,
}: {
  data: Workspace;
  refresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [err, setErr] = useState(""),
    [selected, setSelected] = useState("preview"),
    [confirm, setConfirm] = useState(false);
  const r = data.report,
    base = `${BASE}/cases/${data.case.id}`;
  async function issue() {
    setBusy(true);
    setErr("");
    try {
      const v = await post(
        `/cases/${data.case.id}/runs/${data.run_id}/issue`,
        command(r.fingerprint),
      );
      await refresh();
      setSelected(String(v.version));
      setConfirm(false);
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  const version = data.versions.find((v) => String(v.version) === selected);
  const pdf =
    selected === "preview"
      ? `${base}/runs/${data.run_id}/preview.pdf?revision=${r.fingerprint}`
      : `${base}/versions/${selected}/bulletin.pdf`;
  return (
    <div className="bulletin">
      <div className="review-heading">
        <div>
          <h2>Δελτίο προετοιμασίας</h2>
          <p>
            Η ελεγμένη εικόνα του φακέλου, με τις πηγές και το ιστορικό της.
          </p>
        </div>
        <button className="button primary" onClick={() => setConfirm(true)}>
          <FileCheck2 size={17} />
          {r.draft ? "Έκδοση προσχεδίου" : "Έκδοση δελτίου"}
        </button>
      </div>
      <div className="bulletin-layout">
        <div className="bulletin-preview">
          <div className="preview-bar">
            <label>
              <History size={15} />
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                aria-label="Έκδοση δελτίου"
              >
                <option value="preview">Τρέχουσα προεπισκόπηση</option>
                {data.versions.map((v) => (
                  <option key={v.version} value={v.version}>
                    Έκδοση {v.version} · {dateLabel(v.issued_at)}
                    {v.stale ? " · μη ενημερωμένη" : ""}
                  </option>
                ))}
              </select>
            </label>
            <a className="button text" href={pdf} download>
              <ArrowDownToLine size={15} />
              PDF
            </a>
          </div>
          <PdfReader
            key={pdf}
            url={pdf}
            title={
              selected === "preview"
                ? "Προεπισκόπηση"
                : "Αποθηκευμένη έκδοση " + selected
            }
          />
        </div>
        <aside>
          <section className="panel bulletin-status">
            <span className="eyebrow">
              {version ? "ΑΠΟΘΗΚΕΥΜΕΝΟ ΣΤΙΓΜΙΟΤΥΠΟ" : "ΕΤΟΙΜΟΤΗΤΑ ΔΕΛΤΙΟΥ"}
            </span>
            <div className={"readiness-ring " + (!r.draft ? "complete" : "")}>
              <strong>
                {version ? version.reviewed_count : r.reviewed_count}
                <small>/10</small>
              </strong>
            </div>
            <h3>
              {version
                ? version.draft
                  ? "Αποθηκευμένο προσχέδιο"
                  : "Εκδοθέν δελτίο"
                : r.draft
                  ? "Απομένουν σημεία ελέγχου"
                  : "Έτοιμο για έκδοση"}
            </h3>
            {version?.stale && (
              <Badge tone="amber">Τα στοιχεία έχουν αλλάξει</Badge>
            )}
            <p>
              {version
                ? "Το PDF και οι πηγές ανήκουν στη συγκεκριμένη έκδοση."
                : "Κάθε απαιτούμενο στοιχείο χρειάζεται επαλήθευση και έγκυρη τεκμηρίωση."}
            </p>
          </section>
          {!version && (
            <section className="panel bulletin-issues">
              <h3>Επόμενες ενέργειες</h3>
              {r.issues.length ? (
                r.issues.map((issue: any) => {
                  const f = r.fields.find((x: any) => x.key === issue.id);
                  return (
                    <Link
                      key={issue.id}
                      to={`/cases/${data.case.id}/review?run=${data.run_id}${f ? "&field=" + f.document_type + "." + f.field : "&filter=conflicts"}`}
                    >
                      <CircleAlert size={16} />
                      <span>
                        <b>{issue.label}</b>
                        <small>{issue.reason}</small>
                      </span>
                      <ArrowUpRight size={14} />
                    </Link>
                  );
                })
              ) : (
                <p className="success-text">
                  <Check size={16} />
                  Οι απαιτούμενοι έλεγχοι ολοκληρώθηκαν.
                </p>
              )}
            </section>
          )}
          {version && (
            <section className="panel version-sources">
              <h3>Πηγές της έκδοσης</h3>
              {["application", "financials"].map((kind) => (
                <a
                  target="_blank"
                  rel="noreferrer"
                  key={kind}
                  href={`${base}/versions/${selected}/${kind}.pdf`}
                >
                  <FileText size={16} />
                  {kindLabel(kind)}
                  <ArrowUpRight size={15} />
                </a>
              ))}
              <a href={`${base}/versions/${selected}/snapshot.json`} download>
                Στιγμιότυπο JSON
                <ArrowDownToLine size={15} />
              </a>
            </section>
          )}
          <a
            className="button secondary wide"
            href={`${base}/runs/${data.run_id}/export`}
            download
          >
            <ArrowDownToLine size={16} />
            Εξαγωγή ελεγμένων στοιχείων
          </a>
          <a
            className="button text wide"
            href={`${base}/runs/${data.run_id}/handoff`}
            download
          >
            <ArrowDownToLine size={16} />
            Σύνοψη και διευκρινίσεις
          </a>
        </aside>
      </div>
      {confirm && (
        <Modal
          title={r.draft ? "Έκδοση προσχεδίου" : "Έκδοση δελτίου"}
          onClose={() => setConfirm(false)}
        >
          <p>
            Θα αποθηκευτεί η έκδοση {r.version} μαζί με τα PDF πηγών που
            αντιστοιχούν στον τρέχοντα φάκελο.
          </p>
          {r.draft && (
            <div className="notice amber">
              Υπάρχουν εκκρεμότητες. Η έκδοση θα φέρει ένδειξη ΠΡΟΣΧΕΔΙΟ.
            </div>
          )}
          {err && <ErrorBox error={new Error(err)} />}
          <div className="modal-actions">
            <button
              className="button secondary"
              onClick={() => setConfirm(false)}
            >
              Επιστροφή
            </button>
            <button className="button primary" disabled={busy} onClick={issue}>
              Αποθήκευση έκδοσης
              <Check size={16} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function AnalysisProgress({
  job,
}: {
  job: { state: string; stage?: string; progress: number };
}) {
  const active = ["queued", "running"].includes(job.state);
  const complete = job.state === "complete";
  const stage = complete
    ? 4
    : job.stage === "save"
      ? 3
      : job.stage === "checks"
        ? 2
        : ["application", "financials"].includes(job.stage || "")
          ? 1
          : job.progress >= 96
            ? 3
            : job.progress >= 85
              ? 2
              : job.progress >= 20
                ? 1
                : 0;
  const steps = [
    { label: "Ανάγνωση PDF", detail: "Παραλαβή εγγράφων", Icon: Files },
    { label: "Σάρωση με AI", detail: "Εντοπισμός στοιχείων", Icon: Sparkles },
    {
      label: "Διασταύρωση",
      detail: "Έλεγχος τιμών και πηγών",
      Icon: ShieldCheck,
    },
    { label: "Αποθήκευση", detail: "Οργάνωση αποτελεσμάτων", Icon: FileCheck2 },
  ];
  return (
    <ol
      className={`analysis-flow ${active ? "is-active" : ""}`}
      aria-label="Στάδια ανάλυσης"
    >
      {steps.map(({ label, detail, Icon }, index) => (
        <li
          key={label}
          className={
            index < stage ? "is-done" : index === stage ? "is-current" : ""
          }
          aria-current={active && index === stage ? "step" : undefined}
        >
          <div className="flow-symbol" aria-hidden="true">
            <Icon size={28} strokeWidth={1.5} />
            {index === 1 && <i className="flow-scan" />}
            {index < stage && <Check className="flow-check" size={14} />}
          </div>
          <strong>{label}</strong>
          <small>
            {index < stage
              ? "Ολοκληρώθηκε"
              : index === stage && !active
                ? "Διακόπηκε"
                : detail}
          </small>
          {index < steps.length - 1 && (
            <i className="flow-connector" aria-hidden="true">
              <i />
            </i>
          )}
        </li>
      ))}
    </ol>
  );
}

function CitedClaim({
  text,
  sources,
  onSource,
}: {
  text: string;
  sources: Source[];
  onSource: (source: Source) => void;
}) {
  const [choices, setChoices] = useState<Source[]>([]);
  return (
    <>
      <p>
        {claimParts(text, sources).map((part, index) =>
          part.sources.length ? (
            <button
              type="button"
              className="inline-citation"
              key={index}
              title={
                part.sources.length === 1
                  ? `${part.sources[0].document_name || "Έγγραφο"} · Σελ. ${part.sources[0].page}`
                  : `Προβολή ${part.sources.length} πηγών της πρότασης`
              }
              aria-haspopup={part.sources.length > 1 ? "dialog" : undefined}
              onClick={() =>
                part.sources.length === 1
                  ? onSource(part.sources[0])
                  : setChoices(part.sources)
              }
            >
              {part.text}
            </button>
          ) : (
            <React.Fragment key={index}>{part.text}</React.Fragment>
          ),
        )}
      </p>
      {choices.length > 0 && (
        <Modal title="Πηγές της πρότασης" onClose={() => setChoices([])}>
          <p>
            Η πρόταση βασίζεται σε περισσότερα αποσπάσματα. Επιλέξτε ποιο θέλετε
            να δείτε.
          </p>
          <div className="claim-source-choices">
            {choices.map((source, index) => (
              <button
                type="button"
                className="button secondary"
                key={index}
                onClick={() => {
                  setChoices([]);
                  onSource(source);
                }}
              >
                <strong>
                  {source.document_name || "Έγγραφο"} · Σελ. {source.page}
                </strong>
                <span>
                  {source.quote || source.excerpt || "Προβολή αποσπάσματος"}
                </span>
              </button>
            ))}
          </div>
        </Modal>
      )}
    </>
  );
}

function ChatSources({
  sources,
  onSource,
}: {
  sources: Source[];
  onSource: (s: Source) => void;
}) {
  const groups = new Map<string, Source[]>();
  sources.forEach((s) => {
    const key = `${s.document_id}:${s.page}`;
    const rows = groups.get(key) || [];
    if (!rows.some((r) => (r.quote || r.excerpt) === (s.quote || s.excerpt)))
      rows.push(s);
    groups.set(key, rows);
  });
  if (!groups.size) return null;
  return (
    <details className="chat-sources">
      <summary>
        <FileText size={13} /> Πηγές · {groups.size}{" "}
        {groups.size === 1 ? "σελίδα" : "σελίδες"}
      </summary>
      {[...groups.entries()].map(([key, rows]) => (
        <div className="citation-group" key={key}>
          <strong>
            {rows[0].document_name || "Έγγραφο"} · Σελ. {rows[0].page}
          </strong>
          {rows.map((s, i) => (
            <button key={i} onClick={() => onSource(s)}>
              {s.quote || s.excerpt || "Άνοιγμα αποσπάσματος"}{" "}
              <ArrowUpRight size={13} />
            </button>
          ))}
        </div>
      ))}
    </details>
  );
}

function Chat({
  data,
  context,
  sid,
  setSid,
  onSource,
  onClose,
}: {
  data: Workspace;
  context: FieldValue | null;
  sid: string | null;
  setSid: (sid: string | null) => void;
  onSource: (s: Source) => void;
  onClose: () => void;
}) {
  const chatDisabled = data.execution_mode !== "live";
  const base = `/cases/${data.case.id}/runs/${data.run_id}`;
  const qc = useQueryClient();
  const { data: sessions = [] } = useQuery<any[]>({
    queryKey: ["chats", data.case.id, data.run_id],
    queryFn: () => api(base + "/chats"),
  });
  const [question, setQuestion] = useState(""),
    [busy, setBusy] = useState(false),
    [err, setErr] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const selected = sid ? sessions.find((s) => s.id === sid) : null;
  const turns = selected?.turns || [];
  useEffect(() => {
    if (context)
      setQuestion(
        `Τι αναφέρουν τα έγγραφα για το στοιχείο «${context.label}» (${kindLabel(context.kind)}) του φακέλου;`,
      );
  }, [context]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns.length, busy]);
  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr("");
    try {
      const r = await post(base + "/chat", {
        question: text,
        session_id: selected?.id,
        request_id: crypto.randomUUID(),
      });
      setSid(r.session_id);
      setQuestion("");
      await qc.invalidateQueries({
        queryKey: ["chats", data.case.id, data.run_id],
      });
    } catch (e) {
      setErr(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="assistant">
      <header>
        <span className="assistant-icon">
          <Sparkles size={20} />
        </span>
        <div>
          <h3>Βοηθός φακέλου</h3>
          <small>Απαντήσεις από τα αρχεία του φακέλου</small>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Κλείσιμο βοηθού"
        >
          <X size={18} />
        </button>
      </header>
      <div className="chat-tools">
        <button
          disabled={busy}
          onClick={() => {
            setSid(null);
          }}
        >
          <Plus size={14} />
          Νέα συνομιλία
        </button>
        {sessions.length > 0 && (
          <select
            aria-label="Ιστορικό συνομιλιών"
            value={selected?.id || ""}
            onChange={(e) => {
              setSid(e.target.value);
            }}
          >
            <option value="" disabled>
              Ιστορικό
            </option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.turns[0]?.question?.slice(0, 38) || "Νέα συνομιλία"}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="chat-transcript">
        <p className="muted">
          Ρωτήστε για τα στοιχεία, την ετοιμότητα και τις εκκρεμότητες του
          φακέλου.
        </p>
        {!turns.length && (
          <div className="chat-welcome">
            <Sparkles size={27} />
            <h3>Τι θέλετε να διευκρινίσετε;</h3>
            <p>
              Ρωτήστε για τα στοιχεία του φακέλου και ανοίξτε την πηγή κάθε
              απάντησης.
            </p>
            {[
              "Είναι έτοιμος ο φάκελος;",
              "Τι μένει ανοιχτό;",
              ...data.questions.slice(1, 3),
            ].map((q) => (
              <button key={q} disabled={busy} onClick={() => ask(q)}>
                {q}
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
        )}
        {turns.map((t: any) => (
          <React.Fragment key={t.id}>
            <div className="chat-question">{t.question}</div>
            <article className="chat-answer">
              <span className="chat-answer-label">
                <Sparkles size={13} />
                {t.mode === "local_workflow"
                  ? "Κατάσταση φακέλου"
                  : !t.claims?.length
                    ? "Διευκρίνιση βοηθού"
                    : t.mode === "predefined"
                      ? "Από τα έγγραφα"
                      : "Απάντηση φακέλου"}
              </span>
              {t.message && <p>{t.message}</p>}
              {t.claims?.map((c: any, i: number) => (
                <div key={i}>
                  <CitedClaim
                    text={c.text}
                    sources={c.sources || []}
                    onSource={onSource}
                  />
                  <ChatSources sources={c.sources || []} onSource={onSource} />
                </div>
              ))}
              {t.error && <div className="inline-error">{t.error}</div>}
              {t.suggested_questions?.map((q: string) => (
                <button
                  className="button secondary"
                  key={q}
                  disabled={busy}
                  onClick={() => ask(q)}
                >
                  {q}
                </button>
              ))}
              {t.status === "not_found" && !t.unanswered?.length && (
                <p>Δεν βρέθηκε επαρκής τεκμηρίωση για την ερώτηση.</p>
              )}
              {t.unanswered?.map((u: any, i: number) => (
                <p className="muted" key={i}>
                  {typeof u === "string" ? u : JSON.stringify(u)}
                </p>
              ))}
            </article>
          </React.Fragment>
        ))}
        {busy && (
          <div className="chat-thinking" role="status">
            <span className="spinner" />
            Αναζήτηση και έλεγχος πηγών…
          </div>
        )}
        {err && <ErrorBox error={new Error(err)} />}
        <div ref={bottom} />
      </div>
      <form
        className="chat-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={
            chatDisabled
              ? "Στο demo επιλέξτε μία από τις έτοιμες ερωτήσεις."
              : "Ρωτήστε για τον φάκελο…"
          }
          disabled={chatDisabled}
          aria-label="Ερώτηση προς τον βοηθό"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(question);
            }
          }}
        />
        <button
          disabled={chatDisabled || busy || !question.trim()}
          aria-label="Αποστολή ερώτησης"
        >
          <Send size={17} />
        </button>
      </form>
      <small className="chat-notice">
        {chatDisabled
          ? "Οι έτοιμες ερωτήσεις λειτουργούν με τα στοιχεία του παραδείγματος, χωρίς κλήση AI. Οι απαντήσεις δεν επιβεβαιώνουν στοιχεία."
          : "Νέα ερώτηση μπορεί να χρεωθεί από τον πάροχο AI. Οι έτοιμες ερωτήσεις ανακτώνται τοπικά. Οι απαντήσεις δεν επιβεβαιώνουν στοιχεία."}
      </small>
    </aside>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
