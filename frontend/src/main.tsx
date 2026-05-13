/* eslint-disable react-hooks/exhaustive-deps, react-refresh/only-export-components */
import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Activity,
  BookOpen,
  Boxes,
  Cable,
  FileText,
  Globe2,
  KeyRound,
  Network,
  Play,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users
} from 'lucide-react'
import { api, DocumentItem, ModelConfig, Scan, User, Website } from './lib/api'
import './styles/app.css'

const nav = [
  ['Dashboard', Activity],
  ['Websites', Globe2],
  ['Scans', Play],
  ['Knowledge Graph', Network],
  ['API Docs', BookOpen],
  ['MCP Server', Cable],
  ['AI Models', Sparkles],
  ['Users', Users],
  ['Settings', Settings]
] as const

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [websites, setWebsites] = useState<Website[]>([])
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [models, setModels] = useState<ModelConfig[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [selectedWebsite, setSelectedWebsite] = useState<Website | null>(null)
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null)
  const [scan, setScan] = useState<Scan | null>(null)
  const [url, setUrl] = useState('https://example.com')
  const [companyName, setCompanyName] = useState('Example')
  const [message, setMessage] = useState('Development login gebruikt een e-mailadres als credential.')

  const activeModel = useMemo(() => models.find((model) => model.purpose === 'summary') ?? models[0], [models])

  async function load() {
    const [websiteRows, modelRows, userRows] = await Promise.all([api.websites(), api.models(), api.users().catch(() => [])])
    setWebsites(websiteRows)
    setModels(modelRows)
    setUsers(userRows)
    const website = selectedWebsite ?? websiteRows[0] ?? null
    setSelectedWebsite(website)
    if (website) {
      const docRows = await api.documents(website.id)
      setDocuments(docRows)
      setSelectedDocument(docRows[0] ?? null)
    }
  }

  useEffect(() => {
    api.login('admin@example.com').then(setUser).then(load).catch((error) => setMessage(error.message))
  }, [])

  useEffect(() => {
    if (!scan || ['completed', 'failed'].includes(scan.status)) return
    const timer = window.setInterval(async () => {
      const fresh = await api.getScan(scan.id)
      setScan(fresh)
      if (fresh.status === 'completed' && selectedWebsite) {
        const docRows = await api.documents(selectedWebsite.id)
        setDocuments(docRows)
        setSelectedDocument(docRows[0] ?? null)
      }
    }, 2500)
    return () => window.clearInterval(timer)
  }, [scan, selectedWebsite])

  async function detectName() {
    setMessage('Bedrijfsnaam detecteren...')
    const result = await api.detectCompanyName(url)
    setCompanyName(result.company_name)
    setMessage('Bedrijfsnaam ingevuld op basis van de homepage.')
  }

  async function startScan() {
    let website = websites.find((item) => item.url === url)
    if (!website) {
      website = await api.createWebsite(url, companyName)
      setWebsites([website, ...websites])
    }
    setSelectedWebsite(website)
    const created = await api.startScan(website.id)
    setScan(created)
    setMessage('Scan gestart. De worker verwerkt pagina’s, bestanden, samenvattingen en embeddings.')
  }

  async function resetSelected() {
    if (!selectedWebsite) return
    await api.resetWebsite(selectedWebsite.id)
    setDocuments([])
    setSelectedDocument(null)
    setMessage('Website data is gereset.')
  }

  if (user?.role === 'guest') {
    return (
      <main className="guest-shell">
        <section className="guest-panel">
          <ShieldCheck size={34} />
          <h1>Je account wacht op goedkeuring</h1>
          <p>Je Google login is geregistreerd. Een beheerder moet je nog de rol gebruiker of beheerder geven.</p>
        </section>
      </main>
    )
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><Boxes size={24} /> companycrawler</div>
        <nav>
          {nav.map(([label, Icon], index) => (
            <button className={index === 0 ? 'active' : ''} key={label}><Icon size={17} />{label}</button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>Website intelligence console</h1>
            <p>Publieke bedrijfsdata verzamelen, vectoriseren en ontsluiten.</p>
          </div>
          <div className="user-chip"><KeyRound size={16} /> {user?.email ?? 'loading'} · {user?.role ?? 'admin'}</div>
        </header>

        <section className="grid">
          <div className="panel scan-panel">
            <div className="panel-title"><Globe2 size={18} /> Nieuwe website scan</div>
            <label>Website URL</label>
            <div className="input-row">
              <input value={url} onChange={(event) => setUrl(event.target.value)} onBlur={detectName} />
              <button className="icon-button" onClick={detectName} title="Detecteer bedrijfsnaam"><Search size={17} /></button>
            </div>
            <label>Bedrijfsnaam</label>
            <input value={companyName} onChange={(event) => setCompanyName(event.target.value)} />
            <label>Scan/crawl model</label>
            <select value={activeModel?.id ?? ''} onChange={() => undefined}>
              {models.map((model) => <option key={model.id} value={model.id}>{model.provider} · {model.model}</option>)}
            </select>
            <button className="primary" onClick={startScan}><Play size={17} /> Start scan</button>
            <p className="microcopy">{message}</p>
          </div>

          <div className="panel progress-panel">
            <div className="panel-title"><Activity size={18} /> Scan voortgang</div>
            <div className="progress-ring">{scan?.progress ?? 0}%</div>
            <div className="status-line">{scan?.status ?? 'idle'} · {scan?.message ?? 'Geen actieve scan'}</div>
            <div className="meter"><span style={{ width: `${scan?.progress ?? 0}%` }} /></div>
            <dl>
              <dt>Items gevonden</dt><dd>{scan?.items_found ?? documents.length}</dd>
              <dt>Items verwerkt</dt><dd>{scan?.items_processed ?? documents.length}</dd>
              <dt>Vectorstatus</dt><dd>{documents.filter((doc) => doc.vector_status === 'ready').length}/{documents.length} klaar</dd>
            </dl>
          </div>

          <div className="panel tree-panel">
            <div className="panel-title"><Network size={18} /> Website tree</div>
            <div className="tree">
              {(documents.length ? documents : seedDocuments).map((doc) => (
                <button className={selectedDocument?.id === doc.id ? 'tree-item selected' : 'tree-item'} key={doc.id} onClick={() => setSelectedDocument(doc)}>
                  <FileText size={16} />
                  <span><strong>{doc.title}</strong><small>{doc.display_summary || doc.summary}</small></span>
                </button>
              ))}
            </div>
          </div>

          <div className="panel inspector-panel">
            <div className="panel-title"><FileText size={18} /> Content inspector</div>
            <h2>{selectedDocument?.title ?? 'Homepage'}</h2>
            <p>{selectedDocument?.summary ?? 'Selecteer een pagina of start een scan om samenvattingen en vectorstatus te bekijken.'}</p>
            <dl>
              <dt>Bron</dt><dd>{selectedDocument?.source_url ?? selectedWebsite?.url ?? url}</dd>
              <dt>Type</dt><dd>{selectedDocument?.content_type ?? 'text/html'}</dd>
              <dt>Vector</dt><dd>{selectedDocument?.vector_status ?? 'preview'}</dd>
            </dl>
          </div>

          <div className="panel docs-panel">
            <div className="panel-title"><BookOpen size={18} /> API & MCP</div>
            <a href="/docs" target="_blank">Swagger openen</a>
            <a href="/mcp" target="_blank">MCP manifest openen</a>
            <code>POST /mcp/tools/search_company_data</code>
            <code>POST /api/search</code>
          </div>

          <div className="panel models-panel">
            <div className="panel-title"><Sparkles size={18} /> AI modellen</div>
            <button className="secondary" onClick={() => api.refreshModels().then(setModels)}><RefreshCw size={16} /> Refresh catalogus</button>
            <div className="model-list">
              {models.slice(0, 6).map((model) => <span key={model.id}>{model.provider} · {model.model}<small>{model.best_for}</small></span>)}
            </div>
          </div>

          <div className="panel websites-panel">
            <div className="panel-title"><Globe2 size={18} /> Websites</div>
            {websites.map((website) => (
              <button key={website.id} className={selectedWebsite?.id === website.id ? 'website-row selected' : 'website-row'} onClick={async () => {
                setSelectedWebsite(website)
                const docRows = await api.documents(website.id)
                setDocuments(docRows)
                setSelectedDocument(docRows[0] ?? null)
              }}>
                <span>{website.company_name}<small>{website.url}</small></span>
              </button>
            ))}
            <div className="button-row">
              <button className="secondary" onClick={resetSelected}><RefreshCw size={16} /> Reset</button>
              <button className="danger" onClick={async () => selectedWebsite && api.deleteWebsite(selectedWebsite.id).then(load)}><Trash2 size={16} /> Verwijder</button>
            </div>
          </div>

          <div className="panel users-panel">
            <div className="panel-title"><Users size={18} /> Gebruikers</div>
            {users.slice(0, 5).map((item) => <span className="user-row" key={item.id}>{item.email}<small>{item.role}</small></span>)}
          </div>
        </section>
      </section>
    </main>
  )
}

const seedDocuments: DocumentItem[] = [
  {
    id: 0,
    website_id: 0,
    source_url: 'https://example.com',
    title: 'Homepage',
    content_type: 'text/html',
    file_name: '',
    storage_path: '',
    summary: 'Start een scan om echte content, samenvattingen en embeddings op te bouwen.',
    display_summary: 'Publieke bedrijfsinformatie en kernpositionering.',
    vector_status: 'preview',
    created_at: new Date().toISOString()
  }
]

createRoot(document.getElementById('root')!).render(<App />)
