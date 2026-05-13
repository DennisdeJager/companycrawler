/* eslint-disable react-hooks/exhaustive-deps, react-refresh/only-export-components */
import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Cable,
  CheckCircle2,
  FileText,
  Globe2,
  KeyRound,
  Moon,
  Network,
  Pencil,
  Play,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Sun,
  Trash2,
  Users
} from 'lucide-react'
import { api, DocumentDetail, DocumentItem, ModelConfig, ProviderSettings, Scan, User, Website } from './lib/api'
import smawaLogoSymbol from './assets/smawa-logo-symbol.png'
import './styles/app.css'

type View = 'Dashboard' | 'Websites' | 'Scans' | 'Knowledge Graph' | 'API Docs' | 'MCP Server' | 'AI Models' | 'Users' | 'Settings'

const nav: { label: View; icon: React.ComponentType<{ size?: number }> }[] = [
  { label: 'Dashboard', icon: Activity },
  { label: 'Websites', icon: Globe2 },
  { label: 'Scans', icon: Play },
  { label: 'Knowledge Graph', icon: Network },
  { label: 'API Docs', icon: BookOpen },
  { label: 'MCP Server', icon: Cable },
  { label: 'AI Models', icon: Sparkles },
  { label: 'Users', icon: Users },
  { label: 'Settings', icon: Settings }
]

const emptySettings: ProviderSettings = {
  openai_configured: false,
  openrouter_configured: false,
  google_auth_enabled: false,
  google_client_secret_configured: false,
  google_client_id: '',
  app_url: '',
  app_url_origin: '',
  google_redirect_uri: '',
  google_authorized_domains: [],
  default_summary_provider: 'openai',
  default_summary_model: 'gpt-5.4-mini',
  default_embedding_provider: 'openai',
  default_embedding_model: 'text-embedding-3-small',
  scan_max_items: 500,
  scan_max_file_mb: 25,
  scan_max_depth: 8,
  scan_max_parallel_items: 4,
  warnings: []
}

function App() {
  const [view, setView] = useState<View>('Dashboard')
  const [user, setUser] = useState<User | null>(null)
  const [websites, setWebsites] = useState<Website[]>([])
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [models, setModels] = useState<ModelConfig[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [settings, setSettings] = useState<ProviderSettings>(emptySettings)
  const [selectedWebsite, setSelectedWebsite] = useState<Website | null>(null)
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null)
  const [scan, setScan] = useState<Scan | null>(null)
  const [formUrl, setFormUrl] = useState('https://example.com')
  const [formCompany, setFormCompany] = useState('Example')
  const [formLogoUrl, setFormLogoUrl] = useState('')
  const [editWebsiteId, setEditWebsiteId] = useState<number | null>(null)
  const [message, setMessage] = useState('Klaar om een website te scannen.')
  const [theme, setTheme] = useState<'light' | 'dark'>(() => localStorage.getItem('companycrawler-theme') === 'dark' ? 'dark' : 'light')

  const activeModel = useMemo(() => models.find((model) => model.purpose === 'summary') ?? models[0], [models])

  async function load() {
    const [websiteRows, modelRows, userRows, providerSettings] = await Promise.all([
      api.websites(),
      api.models(),
      api.users().catch(() => []),
      api.providerSettings()
    ])
    setWebsites(websiteRows)
    setModels(modelRows)
    setUsers(userRows)
    setSettings(providerSettings)
    const website = selectedWebsite ? websiteRows.find((item) => item.id === selectedWebsite.id) ?? websiteRows[0] ?? null : websiteRows[0] ?? null
    await selectWebsite(website, false)
  }

  async function selectWebsite(website: Website | null, announce = true) {
    setSelectedWebsite(website)
    if (!website) {
      setDocuments([])
      setSelectedDocument(null)
      return
    }
    setFormUrl(website.url)
    setFormCompany(website.company_name)
    setFormLogoUrl(website.logo_url ?? '')
    const docRows = await api.documents(website.id)
    setDocuments(docRows)
    setSelectedDocument(docRows[0] ?? null)
    if (announce) setMessage(`${website.company_name} is actief geselecteerd.`)
  }

  useEffect(() => {
    api.providerSettings()
      .then(async (providerSettings) => {
        setSettings(providerSettings)
        if (!providerSettings.google_auth_enabled) {
          return api.login('admin@example.com').then(setUser).then(load)
        }
        const loggedIn = await api.session().catch(() => null)
        if (loggedIn) {
          setUser(loggedIn)
          await load()
        }
        return undefined
      })
      .catch((error) => setMessage(error.message))
  }, [])

  useEffect(() => {
    if (!scan || ['completed', 'failed'].includes(scan.status)) return
    const timer = window.setInterval(async () => {
      const fresh = await api.getScan(scan.id)
      setScan(fresh)
      if (selectedWebsite) {
        const docRows = await api.documents(selectedWebsite.id)
        setDocuments(docRows)
        setSelectedDocument((current) => current ?? docRows[0] ?? null)
      }
      if (fresh.status === 'completed') setMessage('Scan afgerond. De website tree is bijgewerkt.')
      if (fresh.status === 'failed') setMessage(`Scan mislukt: ${fresh.error || fresh.message}`)
    }, 1200)
    return () => window.clearInterval(timer)
  }, [scan, selectedWebsite])

  async function detectName() {
    setMessage('Bedrijfsnaam detecteren...')
    try {
      const result = await api.detectCompanyName(formUrl)
      setFormCompany(result.company_name)
      setFormLogoUrl(result.logo_url ?? '')
      setMessage('Bedrijfsnaam ingevuld op basis van de homepage.')
    } catch (error) {
      setMessage(`Detectie mislukt: ${String(error)}`)
    }
  }

  async function saveWebsite() {
    if (editWebsiteId) {
      const updated = await api.updateWebsite(editWebsiteId, { url: formUrl, company_name: formCompany, logo_url: formLogoUrl })
      setWebsites((rows) => rows.map((item) => (item.id === updated.id ? updated : item)))
      await selectWebsite(updated)
      setEditWebsiteId(null)
      setMessage('Website bijgewerkt.')
      return updated
    }
    const created = await api.createWebsite(formUrl, formCompany, formLogoUrl)
    setWebsites((rows) => [created, ...rows])
    await selectWebsite(created)
    setMessage('Website aangemaakt en actief geselecteerd.')
    return created
  }

  async function startScan() {
    const website = selectedWebsite?.url === formUrl && !editWebsiteId ? selectedWebsite : await saveWebsite()
    setScan({
      id: 0,
      website_id: website.id,
      status: 'queued',
      progress: 0,
      message: 'Scan wordt gestart...',
      items_found: 0,
      items_processed: 0,
      error: '',
      created_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
      duration_seconds: 0,
      normal_db_size_mb: 0,
      vector_db_size_mb: 0,
      scan_max_parallel_items: settings.scan_max_parallel_items
    })
    setView('Dashboard')
    const created = await api.startScan(website.id)
    setScan(created)
    setMessage('Scan gestart. Voortgang wordt realtime bijgewerkt.')
  }

  async function deleteWebsite(website: Website) {
    await api.deleteWebsite(website.id)
    const rows = websites.filter((item) => item.id !== website.id)
    setWebsites(rows)
    await selectWebsite(rows[0] ?? null)
    setMessage('Website verwijderd.')
  }

  async function resetSelected() {
    if (!selectedWebsite) return
    await api.resetWebsite(selectedWebsite.id)
    setDocuments([])
    setSelectedDocument(null)
    setMessage('Alle crawl-data voor deze website is verwijderd.')
  }

  function toggleTheme() {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark'
      localStorage.setItem('companycrawler-theme', next)
      return next
    })
  }

  if (!user && settings.google_auth_enabled) {
    return (
      <main className="guest-shell">
        <section className="guest-panel">
          <ShieldCheck size={34} />
          <h1>Inloggen met Google</h1>
          <p>Gebruik je Google account om toegang tot companycrawler aan te vragen.</p>
          <a className="google-login-button" href="/api/auth/google/start">Inloggen met Google</a>
          <GoogleOriginDiagnostics settings={settings} />
        </section>
      </main>
    )
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
    <main className={`app-shell theme-${theme}`}>
      <aside className="sidebar">
        <div className="brand">
          <img src={smawaLogoSymbol} alt="Smawa" />
          <span>companycrawler</span>
        </div>
        <nav>
          {nav.map(({ label, icon: Icon }) => (
            <button className={view === label ? 'active' : ''} key={label} onClick={() => setView(label)}>
              <Icon size={17} />{label}
            </button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            {selectedWebsite?.logo_url && <img className="company-logo" src={selectedWebsite.logo_url} alt={`${selectedWebsite.company_name} logo`} />}
            <div>
            <h1>{view}</h1>
            <p>{selectedWebsite ? `${selectedWebsite.company_name} · ${selectedWebsite.url}` : 'Geen actieve website geselecteerd.'}</p>
            </div>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" onClick={toggleTheme} title={theme === 'dark' ? 'Licht thema' : 'Donker thema'}>
              {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <div className="user-chip"><KeyRound size={16} /> {user?.email ?? 'loading'} · {user?.role ?? 'admin'}</div>
          </div>
        </header>

        {settings.warnings.length > 0 && <Warnings warnings={settings.warnings} onSettings={() => setView('Settings')} />}

        {view === 'Dashboard' && (
          <Dashboard
            documents={documents}
            message={message}
            scan={scan}
            selectedDocument={selectedDocument}
            selectedWebsite={selectedWebsite}
            setSelectedDocument={setSelectedDocument}
          />
        )}

        {view === 'Websites' && (
          <WebsitesView
            company={formCompany}
            deleteWebsite={deleteWebsite}
            detectName={detectName}
            editWebsiteId={editWebsiteId}
            resetSelected={resetSelected}
            saveWebsite={saveWebsite}
            selectedWebsite={selectedWebsite}
            selectWebsite={selectWebsite}
            setCompany={setFormCompany}
            setEditWebsiteId={setEditWebsiteId}
            setLogoUrl={setFormLogoUrl}
            setUrl={setFormUrl}
            startScan={startScan}
            logoUrl={formLogoUrl}
            url={formUrl}
            websites={websites}
          />
        )}

        {view === 'Scans' && <ScansView activeModel={activeModel} message={message} scan={scan} startScan={startScan} />}
        {view === 'Knowledge Graph' && <KnowledgeView documents={documents} selectedDocument={selectedDocument} selectedWebsite={selectedWebsite} setSelectedDocument={setSelectedDocument} />}
        {view === 'API Docs' && <DocsView />}
        {view === 'MCP Server' && <McpView />}
        {view === 'AI Models' && <ModelsView models={models} refresh={async () => setModels(await api.refreshModels())} />}
        {view === 'Users' && <UsersView users={users} refresh={async () => setUsers(await api.users())} />}
        {view === 'Settings' && (
          <SettingsView
            key={`${settings.google_client_id}:${settings.app_url_origin}:${settings.default_summary_model}:${settings.default_embedding_model}`}
            settings={settings}
            setSettings={setSettings}
            refresh={load}
          />
        )}
      </section>
    </main>
  )
}

function Warnings({ warnings, onSettings }: { warnings: string[]; onSettings: () => void }) {
  return (
    <section className="warning-strip">
      <AlertTriangle size={18} />
      <div>{warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>
      <button className="secondary" onClick={onSettings}>Open instellingen</button>
    </section>
  )
}

function Dashboard(props: {
  documents: DocumentItem[]
  message: string
  scan: Scan | null
  selectedDocument: DocumentItem | null
  selectedWebsite: Website | null
  setSelectedDocument: (doc: DocumentItem) => void
}) {
  return (
    <section className="dashboard-layout">
      <ProgressPanel scan={props.scan} documents={props.documents} message={props.message} />
      <TreePanel documents={props.documents} selectedDocument={props.selectedDocument} setSelectedDocument={props.setSelectedDocument} />
      <Inspector document={props.selectedDocument} website={props.selectedWebsite} />
    </section>
  )
}

function secondsBetween(start?: string | null, end?: string | null) {
  if (!start) return 0
  const started = new Date(start).getTime()
  const ended = end ? new Date(end).getTime() : Date.now()
  if (Number.isNaN(started) || Number.isNaN(ended)) return 0
  return Math.max(0, Math.floor((ended - started) / 1000))
}

function formatDuration(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${hours}u ${minutes}m ${seconds}s`
}

function formatMb(value: number) {
  return `${value.toFixed(2)} MB`
}

function ProgressPanel({ scan, documents, message }: { scan: Scan | null; documents: DocumentItem[]; message: string }) {
  const statusText = scan?.status === 'failed' ? scan.error || scan.message : scan?.message ?? message
  const elapsedSeconds = scan ? scan.duration_seconds || secondsBetween(scan.started_at ?? scan.created_at, scan.completed_at) : 0
  return (
    <div className={scan?.status === 'running' ? 'panel progress-panel scanning' : 'panel progress-panel'}>
      <div className="panel-title"><Activity size={18} /> Realtime scan voortgang</div>
      <div className="progress-ring">{scan?.progress ?? 0}%</div>
      <div className="status-line">{scan?.status ?? 'idle'} · {statusText}</div>
      {scan?.error && <pre className="scan-error">{scan.error}</pre>}
      <div className="meter"><span style={{ width: `${scan?.progress ?? 0}%` }} /></div>
      <dl>
        <dt>Items gevonden</dt><dd>{scan?.items_found ?? documents.length}</dd>
        <dt>Items verwerkt</dt><dd>{scan?.items_processed ?? documents.length}</dd>
        <dt>Vectorstatus</dt><dd>{documents.filter((doc) => doc.vector_status === 'ready').length}/{documents.length} klaar</dd>
        <dt>Looptijd</dt><dd>{formatDuration(elapsedSeconds)}</dd>
        <dt>Normale DB</dt><dd>{formatMb(scan?.normal_db_size_mb ?? 0)}</dd>
        <dt>Vector DB</dt><dd>{formatMb(scan?.vector_db_size_mb ?? 0)}</dd>
        <dt>Parallel</dt><dd>{scan?.scan_max_parallel_items ?? '-'} taken</dd>
      </dl>
    </div>
  )
}

function TreePanel({ documents, selectedDocument, setSelectedDocument }: { documents: DocumentItem[]; selectedDocument: DocumentItem | null; setSelectedDocument: (doc: DocumentItem) => void }) {
  const tree = useMemo(() => buildDocumentTree(documents.length ? documents : seedDocuments), [documents])
  return (
    <div className="panel tree-panel">
      <div className="panel-title"><Network size={18} /> Website tree</div>
      <div className="tree">
        {tree.map((node) => (
          <TreeNodeView key={node.id} node={node} selectedDocument={selectedDocument} setSelectedDocument={setSelectedDocument} />
        ))}
      </div>
    </div>
  )
}

type DocumentTreeNode = {
  id: string
  label: string
  document?: DocumentItem
  children: DocumentTreeNode[]
}

function TreeNodeView({ node, selectedDocument, setSelectedDocument, depth = 0 }: { node: DocumentTreeNode; selectedDocument: DocumentItem | null; setSelectedDocument: (doc: DocumentItem) => void; depth?: number }) {
  const [open, setOpen] = useState(true)
  const hasChildren = node.children.length > 0
  const isSelected = Boolean(node.document && selectedDocument?.id === node.document.id)

  return (
    <div className="tree-node">
      <button
        className={isSelected ? 'tree-row selected' : 'tree-row'}
        style={{ paddingLeft: 10 + depth * 16 }}
        onClick={() => node.document ? setSelectedDocument(node.document) : setOpen((current) => !current)}
      >
        <span className={hasChildren ? 'tree-toggle' : 'tree-toggle empty'}>{hasChildren ? (open ? 'v' : '>') : ''}</span>
        <FileText size={15} />
        <span>
          <strong>{node.document ? compactTitle(node.document.title || node.label, 68) : node.label}</strong>
          <small>{node.document ? (node.document.display_summary || node.document.summary) : `${countTreeDocuments(node)} item${countTreeDocuments(node) === 1 ? '' : 's'}`}</small>
        </span>
      </button>
      {open && hasChildren && (
        <div className="tree-children">
          {node.children.map((child) => (
            <TreeNodeView key={child.id} node={child} selectedDocument={selectedDocument} setSelectedDocument={setSelectedDocument} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function buildDocumentTree(documents: DocumentItem[]) {
  const root: DocumentTreeNode = { id: 'root', label: 'Website', children: [] }
  for (const document of uniqueDocuments(documents)) {
    const pathParts = documentPathParts(document)
    let current = root
    for (const part of pathParts.slice(0, -1)) {
      const id = `${current.id}/${part}`
      let next = current.children.find((child) => child.id === id && !child.document)
      if (!next) {
        next = { id, label: part, children: [] }
        current.children.push(next)
      }
      current = next
    }
    const label = pathParts[pathParts.length - 1] || document.title || 'Home'
    current.children.push({ id: `doc-${document.id}`, label, document, children: [] })
  }
  sortTree(root)
  return root.children
}

function documentPathParts(document: DocumentItem) {
  try {
    const parsed = new URL(document.source_url)
    const parts = parsed.pathname.split('/').filter(Boolean).map((part) => part.replace(/[-_]+/g, ' '))
    return parts.length ? parts : ['Home']
  } catch {
    return [document.title || 'Document']
  }
}

function sortTree(node: DocumentTreeNode) {
  node.children.sort((left, right) => {
    if (left.document && !right.document) return 1
    if (!left.document && right.document) return -1
    return left.label.localeCompare(right.label)
  })
  node.children.forEach(sortTree)
}

function countTreeDocuments(node: DocumentTreeNode): number {
  return (node.document ? 1 : 0) + node.children.reduce((total, child) => total + countTreeDocuments(child), 0)
}

function Inspector({ document, website }: { document: (DocumentItem | DocumentDetail) | null; website: Website | null }) {
  const fullText = document && 'text_content' in document ? document.text_content : ''
  return (
    <div className="panel inspector-panel">
      <div className="panel-title"><FileText size={18} /> Content inspector</div>
      <h2>{document?.title ?? 'Nog geen content'}</h2>
      <p>{document?.summary ?? 'Start een scan of selecteer een document uit de website tree.'}</p>
      <dl>
        <dt>Website</dt><dd>{website?.company_name ?? 'Geen selectie'}</dd>
        <dt>Bron</dt><dd>{document?.source_url ?? website?.url ?? '-'}</dd>
        <dt>Type</dt><dd>{document?.content_type ?? '-'}</dd>
        <dt>Vector</dt><dd>{document?.vector_status ?? '-'}</dd>
      </dl>
      {fullText && (
        <div className="full-text-block">
          <strong>Volledige tekst</strong>
          <p>{fullText}</p>
        </div>
      )}
    </div>
  )
}

function WebsitesView(props: {
  company: string
  deleteWebsite: (website: Website) => void
  detectName: () => void
  editWebsiteId: number | null
  logoUrl: string
  resetSelected: () => void
  saveWebsite: () => void
  selectedWebsite: Website | null
  selectWebsite: (website: Website) => void
  setCompany: (value: string) => void
  setEditWebsiteId: (id: number | null) => void
  setLogoUrl: (value: string) => void
  setUrl: (value: string) => void
  startScan: () => void
  url: string
  websites: Website[]
}) {
  return (
    <section className="split-layout">
      <div className="panel">
        <div className="panel-title"><Globe2 size={18} /> Websites</div>
        <div className="website-list">
          {props.websites.map((website) => (
            <div className={props.selectedWebsite?.id === website.id ? 'website-card selected' : 'website-card'} key={website.id}>
              <button onClick={() => props.selectWebsite(website)}>
                <span className="website-card-title">
                  {website.logo_url && <img src={website.logo_url} alt="" />}
                  <strong>{website.company_name}</strong>
                </span>
                <small>{website.url}</small>
              </button>
              <div className="row-actions">
                <button title="Bewerken" onClick={() => {
                  props.setEditWebsiteId(website.id)
                  props.setUrl(website.url)
                  props.setCompany(website.company_name)
                  props.setLogoUrl(website.logo_url ?? '')
                }}><Pencil size={16} /></button>
                <button title="Verwijderen" onClick={() => props.deleteWebsite(website)}><Trash2 size={16} /></button>
              </div>
            </div>
          ))}
          {props.websites.length === 0 && <p className="empty">Nog geen websites. Maak rechts je eerste website aan.</p>}
        </div>
      </div>

      <div className="panel form-panel">
        <div className="panel-title"><Save size={18} /> {props.editWebsiteId ? 'Website bewerken' : 'Nieuwe website'}</div>
        <label>Website URL</label>
        <div className="input-row">
          <input value={props.url} onChange={(event) => props.setUrl(event.target.value)} />
          <button className="icon-button" onClick={props.detectName} title="Detecteer bedrijfsnaam"><Search size={17} /></button>
        </div>
        <label>Bedrijfsnaam</label>
        <input value={props.company} onChange={(event) => props.setCompany(event.target.value)} />
        <label>Logo URL</label>
        <div className="input-row">
          <input value={props.logoUrl} onChange={(event) => props.setLogoUrl(event.target.value)} placeholder="Automatisch gevonden of handmatig invullen" />
          <span className="logo-preview">{props.logoUrl ? <img src={props.logoUrl} alt="" /> : null}</span>
        </div>
        <div className="button-row">
          <button className="primary" onClick={props.saveWebsite}><Save size={17} /> Opslaan</button>
          <button className="secondary" onClick={props.startScan}><Play size={17} /> Start scan</button>
        </div>
        <div className="button-row">
          <button className="secondary" onClick={() => {
            props.setEditWebsiteId(null)
            props.setLogoUrl('')
          }}>Nieuw formulier</button>
          <button className="danger" onClick={props.resetSelected}><RefreshCw size={16} /> Reset actieve website</button>
        </div>
      </div>
    </section>
  )
}

function ScansView({ activeModel, message, scan, startScan }: { activeModel?: ModelConfig; message: string; scan: Scan | null; startScan: () => void }) {
  return (
    <section className="split-layout">
      <ProgressPanel scan={scan} documents={[]} message={message} />
      <div className="panel">
        <div className="panel-title"><Play size={18} /> Scan bediening</div>
        <p className="body-text">Start een scan voor de actieve website. De voortgang verschijnt direct op Dashboard en hier.</p>
        <dl>
          <dt>Model</dt><dd>{activeModel ? `${activeModel.provider} · ${activeModel.model}` : 'Geen model geladen'}</dd>
          <dt>Status</dt><dd>{scan?.status ?? 'idle'}</dd>
        </dl>
        <button className="primary" onClick={startScan}><Play size={17} /> Start scan</button>
      </div>
    </section>
  )
}

type MindNode = {
  id: string
  title: string
  subtitle: string
  x: number
  y: number
  width: number
  height: number
  document?: DocumentItem
  kind: 'root' | 'group' | 'document'
  depth: number
}

type MindEdge = {
  from: MindNode
  to: MindNode
}

function KnowledgeView(props: { documents: DocumentItem[]; selectedDocument: DocumentItem | null; selectedWebsite: Website | null; setSelectedDocument: (doc: DocumentItem) => void }) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null)
  const graph = useMemo(() => buildMindmap(props.documents, props.selectedWebsite), [props.documents, props.selectedWebsite])

  useEffect(() => {
    if (!props.selectedDocument?.id) return
    let cancelled = false
    api.document(props.selectedDocument.id)
      .then((document) => {
        if (!cancelled) setDetail(document)
      })
      .catch(() => {
        if (!cancelled) setDetail(null)
      })
    return () => {
      cancelled = true
    }
  }, [props.selectedDocument?.id])

  return (
    <section className="knowledge-layout">
      <div className="panel mindmap-panel">
        <div className="panel-title"><Network size={18} /> Website mindmap</div>
        <div className="mindmap-canvas" style={{ width: graph.width, height: graph.height }}>
          <svg className="mindmap-lines" width={graph.width} height={graph.height} aria-hidden="true">
            {graph.edges.map((edge) => (
              <path
                key={`${edge.from.id}-${edge.to.id}`}
                d={connectorPath(edge.from, edge.to)}
                fill="none"
              />
            ))}
          </svg>
          {graph.nodes.map((node) => (
            <button
              className={[
                'mind-node',
                `mind-node-${node.kind}`,
                node.document && props.selectedDocument?.id === node.document.id ? 'selected' : ''
              ].filter(Boolean).join(' ')}
              key={node.id}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
              onClick={() => node.document && props.setSelectedDocument(node.document)}
              disabled={!node.document}
              title={node.document?.source_url || node.title}
            >
              <strong>{node.title}</strong>
              <small>{node.subtitle}</small>
            </button>
          ))}
        </div>
      </div>
      <Inspector document={detail?.id === props.selectedDocument?.id ? detail : props.selectedDocument} website={props.selectedWebsite} />
    </section>
  )
}

function buildMindmap(documents: DocumentItem[], website: Website | null) {
  const nodeWidth = 230
  const nodeHeight = 70
  const columnGap = 72
  const rowGap = 16
  let cursorY = 22
  const nodes: MindNode[] = []
  const edges: MindEdge[] = []
  const treeRoot = buildDocumentTree(uniqueDocuments(documents))
  let maxDepth = 0

  const rootNode: MindNode = {
    id: 'root',
    title: compactTitle(website?.company_name || 'Website'),
    subtitle: documents.length ? `${uniqueDocuments(documents).length} unieke items` : 'Geen crawl-data',
    x: 24,
    y: 22,
    width: 220,
    height: nodeHeight,
    kind: 'root',
    depth: 0
  }
  nodes.push(rootNode)

  function placeTreeNode(treeNode: DocumentTreeNode, parent: MindNode, depth: number): MindNode {
    maxDepth = Math.max(maxDepth, depth)
    const document = treeNode.document
    const mindNode: MindNode = {
      id: document ? `doc-${document.id}` : `group-${treeNode.id}`,
      title: compactTitle(document ? (document.title || treeNode.label) : treeNode.label, 54),
      subtitle: document ? compactTitle(document.display_summary || document.summary || document.source_url, 72) : `${countTreeDocuments(treeNode)} item${countTreeDocuments(treeNode) === 1 ? '' : 's'}`,
      x: 24 + depth * (nodeWidth + columnGap),
      y: cursorY,
      width: nodeWidth,
      height: nodeHeight,
      document,
      kind: document ? 'document' : 'group',
      depth
    }
    cursorY += nodeHeight + rowGap
    nodes.push(mindNode)
    edges.push({ from: parent, to: mindNode })
    for (const child of treeNode.children) {
      placeTreeNode(child, mindNode, depth + 1)
    }
    return mindNode
  }

  for (const child of treeRoot) {
    placeTreeNode(child, rootNode, 1)
  }

  const height = Math.max(360, cursorY + 20)
  rootNode.y = Math.max(22, height / 2 - nodeHeight / 2)
  return { nodes, edges, width: Math.max(840, 48 + (maxDepth + 1) * nodeWidth + maxDepth * columnGap), height }
}

function uniqueDocuments(documents: DocumentItem[]) {
  const byUrl = new Map<string, DocumentItem>()
  for (const document of documents) {
    const key = canonicalFrontendUrl(document.source_url)
    if (!byUrl.has(key)) byUrl.set(key, document)
  }
  return Array.from(byUrl.values())
}

function canonicalFrontendUrl(value: string) {
  try {
    const parsed = new URL(value)
    parsed.hash = ''
    parsed.hostname = parsed.hostname.replace(/^www\./, '').toLowerCase()
    if (parsed.pathname === '/') parsed.pathname = ''
    return parsed.toString()
  } catch {
    return value
  }
}

function compactTitle(value: string, max = 52) {
  const clean = value.replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max - 1)}...` : clean
}

function connectorPath(from: MindNode, to: MindNode) {
  const startX = from.x + from.width
  const startY = from.y + from.height / 2
  const endX = to.x
  const endY = to.y + to.height / 2
  const mid = Math.max(40, (endX - startX) / 2)
  return `M ${startX} ${startY} C ${startX + mid} ${startY}, ${endX - mid} ${endY}, ${endX} ${endY}`
}

function DocsView() {
  return (
    <section className="panel docs-panel wide">
      <div className="panel-title"><BookOpen size={18} /> API documentatie</div>
      <a href="/docs" target="_blank">Swagger UI openen</a>
      <a href="/openapi.json" target="_blank">OpenAPI JSON openen</a>
      <code>POST /api/scans</code>
      <code>GET /api/websites/{'{website_id}'}/documents</code>
      <code>POST /api/search</code>
    </section>
  )
}

function McpView() {
  return (
    <section className="panel docs-panel wide">
      <div className="panel-title"><Cable size={18} /> MCP server</div>
      <a href="/mcp" target="_blank">MCP manifest openen</a>
      <code>POST /mcp/tools/list_websites</code>
      <code>POST /mcp/tools/start_scan</code>
      <code>POST /mcp/tools/get_scan_status</code>
      <code>POST /mcp/tools/search_company_data</code>
      <code>POST /mcp/tools/get_company_profile</code>
    </section>
  )
}

function ModelsView({ models, refresh }: { models: ModelConfig[]; refresh: () => void }) {
  return (
    <section className="panel wide">
      <div className="panel-title"><Sparkles size={18} /> AI modellen</div>
      <button className="secondary" onClick={refresh}><RefreshCw size={16} /> Refresh catalogus</button>
      <div className="table-list">
        {models.map((model) => (
          <div className="table-row" key={model.id}>
            <strong>{model.provider} · {model.model}</strong>
            <span>{model.purpose}</span>
            <small>{model.best_for}</small>
          </div>
        ))}
      </div>
    </section>
  )
}

function UsersView({ users, refresh }: { users: User[]; refresh: () => void }) {
  async function setRole(user: User, role: string) {
    await api.updateUserRole(user.id, role)
    await refresh()
  }
  return (
    <section className="panel wide">
      <div className="panel-title"><Users size={18} /> User management</div>
      <div className="table-list">
        {users.map((item) => (
          <div className="table-row user-management-row" key={item.id}>
            <strong>{item.email}</strong>
            <span>{item.name || '-'}</span>
            <select value={item.role} onChange={(event) => setRole(item, event.target.value)}>
              <option value="guest">guest</option>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </div>
        ))}
      </div>
    </section>
  )
}

function SettingsView({ settings, setSettings, refresh }: { settings: ProviderSettings; setSettings: (settings: ProviderSettings) => void; refresh: () => void }) {
  const [openaiKey, setOpenaiKey] = useState('')
  const [openrouterKey, setOpenrouterKey] = useState('')
  const [googleClientId, setGoogleClientId] = useState(settings.google_client_id)
  const [googleClientSecret, setGoogleClientSecret] = useState('')
  const [summaryModel, setSummaryModel] = useState(settings.default_summary_model)
  const [embeddingModel, setEmbeddingModel] = useState(settings.default_embedding_model)
  const [scanMaxItems, setScanMaxItems] = useState(settings.scan_max_items)
  const [scanMaxFileMb, setScanMaxFileMb] = useState(settings.scan_max_file_mb)
  const [scanMaxDepth, setScanMaxDepth] = useState(settings.scan_max_depth)
  const [scanMaxParallelItems, setScanMaxParallelItems] = useState(settings.scan_max_parallel_items)

  async function save() {
    const saved = await api.saveProviderSettings({
      openai_api_key: openaiKey,
      openrouter_api_key: openrouterKey,
      google_client_id: googleClientId,
      google_client_secret: googleClientSecret,
      default_summary_provider: settings.default_summary_provider,
      default_summary_model: summaryModel,
      default_embedding_provider: settings.default_embedding_provider,
      default_embedding_model: embeddingModel,
      scan_max_items: scanMaxItems,
      scan_max_file_mb: scanMaxFileMb,
      scan_max_depth: scanMaxDepth,
      scan_max_parallel_items: scanMaxParallelItems
    })
    setSettings(saved)
    setOpenaiKey('')
    setOpenrouterKey('')
    setGoogleClientSecret('')
    await refresh()
  }

  return (
    <section className="split-layout">
      <div className="panel form-panel">
        <div className="panel-title"><KeyRound size={18} /> Provider instellingen</div>
        <StatusLine ok={settings.openai_configured} label="OpenAI API key" />
        <label>Nieuwe OpenAI API key</label>
        <input type="password" value={openaiKey} onChange={(event) => setOpenaiKey(event.target.value)} placeholder={settings.openai_configured ? 'Ingesteld, laat leeg om te behouden' : 'sk-...'} />
        <StatusLine ok={settings.openrouter_configured} label="OpenRouter API key" />
        <label>Nieuwe OpenRouter API key</label>
        <input type="password" value={openrouterKey} onChange={(event) => setOpenrouterKey(event.target.value)} placeholder={settings.openrouter_configured ? 'Ingesteld, laat leeg om te behouden' : 'sk-or-...'} />
        <label>Default summary model</label>
        <input value={summaryModel} onChange={(event) => setSummaryModel(event.target.value)} />
        <label>Default embedding model</label>
        <input value={embeddingModel} onChange={(event) => setEmbeddingModel(event.target.value)} />
        <button className="primary" onClick={save}><Save size={17} /> Instellingen opslaan</button>
      </div>
      <div className="panel form-panel">
        <div className="panel-title"><ShieldCheck size={18} /> Google authenticatie</div>
        <StatusLine ok={settings.google_auth_enabled} label="Google login" />
        <label>Google Client ID</label>
        <input value={googleClientId} onChange={(event) => setGoogleClientId(event.target.value)} placeholder="Google OAuth Client ID" />
        <GoogleOriginDiagnostics settings={settings} />
        <StatusLine ok={settings.google_client_secret_configured} label="Google Client Secret" />
        <label>Google Client Secret</label>
        <input type="password" value={googleClientSecret} onChange={(event) => setGoogleClientSecret(event.target.value)} placeholder={settings.google_client_secret_configured ? 'Ingesteld, laat leeg om te behouden' : 'Vereist voor server-side redirect login'} />
        <p className="body-text">De backend wisselt de Google authorization code om voor een ID token en zet daarna een sessiecookie. Secrets worden alleen in .env opgeslagen en niet teruggetoond.</p>
        <div className="settings-divider" />
        <div className="panel-title"><Network size={18} /> Crawl instellingen</div>
        <NumberSetting
          label="Max items"
          value={scanMaxItems}
          setValue={setScanMaxItems}
          help="Maximum aantal unieke URL's of documenten dat een scan verwerkt. Hoger geeft completere scans, maar duurt langer."
        />
        <NumberSetting
          label="Max file MB"
          value={scanMaxFileMb}
          setValue={setScanMaxFileMb}
          help="Maximale grootte van een bestand dat wordt gedownload. Grotere PDF's of documenten worden overgeslagen."
        />
        <NumberSetting
          label="Max depth"
          value={scanMaxDepth}
          setValue={setScanMaxDepth}
          help="Maximale klikdiepte vanaf de startpagina. Diepte 1 zijn links op de homepage, diepte 2 links daarvandaan."
        />
        <NumberSetting
          label="Parallel items"
          value={scanMaxParallelItems}
          setValue={setScanMaxParallelItems}
          help="Aantal pagina's of bestanden dat tegelijk wordt opgehaald, samengevat en gevectoriseerd."
        />
        <button className="primary" onClick={save}><Save size={17} /> Instellingen opslaan</button>
      </div>
    </section>
  )
}

function NumberSetting({ label, value, setValue, help }: { label: string; value: number; setValue: (value: number) => void; help: string }) {
  return (
    <div className="number-setting">
      <label>{label}</label>
      <input type="number" min={1} value={value} onChange={(event) => setValue(Math.max(1, Number(event.target.value) || 1))} />
      <small>{help}</small>
    </div>
  )
}

function GoogleOriginDiagnostics({ settings }: { settings: ProviderSettings }) {
  const browserOrigin = window.location.origin
  const requiredDomains = settings.google_authorized_domains
  const appUrlMismatch = Boolean(settings.app_url_origin && browserOrigin !== settings.app_url_origin)

  return (
    <div className="diagnostic-box">
      <strong>Google Cloud redirect</strong>
      <dl>
        <dt>Browser origin</dt><dd>{browserOrigin}</dd>
        <dt>APP_URL origin</dt><dd>{settings.app_url_origin || 'Niet ingesteld'}</dd>
        <dt>Redirect URI</dt><dd>{settings.google_redirect_uri || 'Niet ingesteld'}</dd>
      </dl>
      {appUrlMismatch && <p className="inline-warning">APP_URL komt niet overeen met de origin waarop je deze console gebruikt.</p>}
      <p className="body-text">Zet deze Authorized redirect URI in Google Cloud bij deze Web application Client ID:</p>
      <div className="origin-list">
        <code>{settings.google_redirect_uri || '-'}</code>
      </div>
      <p className="body-text">Authorized JavaScript origins zijn niet nodig voor deze server-side redirect-flow.</p>
      <p className="body-text">Voeg bij Authorized domains toe: {requiredDomains.length ? requiredDomains.join(', ') : 'het hoofddomein van APP_URL'}.</p>
    </div>
  )
}

function StatusLine({ ok, label }: { ok: boolean; label: string }) {
  return <div className={ok ? 'status-ok' : 'status-warn'}>{ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}{label}: {ok ? 'ingesteld' : 'niet ingesteld'}</div>
}

const seedDocuments: DocumentItem[] = [
  {
    id: 0,
    website_id: 0,
    source_url: '',
    title: 'Geen crawl-data',
    content_type: 'text/html',
    file_name: '',
    storage_path: '',
    text_hash: '',
    summary: 'Start een scan om pagina’s, bestanden, samenvattingen en embeddings te verzamelen.',
    display_summary: 'Nog geen website tree beschikbaar.',
    vector_status: 'pending',
    created_at: new Date().toISOString()
  }
]

createRoot(document.getElementById('root')!).render(<App />)
