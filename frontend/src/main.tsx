/* eslint-disable react-hooks/exhaustive-deps, react-refresh/only-export-components */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Activity,
  AlertTriangle,
  BookOpen,
  Cable,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  ClipboardList,
  FileText,
  Globe2,
  KeyRound,
  Maximize2,
  Minus,
  Moon,
  Move,
  Network,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Trash2,
  Users,
  X
} from 'lucide-react'
import smawaLogoDark from './assets/smawa-logo-light-transparent.png'
import smawaLogoLight from './assets/smawa-logo-background-white.png'
import { api, DocumentDetail, DocumentItem, ModelConfig, ProviderSettings, Scan, User, Website } from './lib/api'
import type { AnalysisPrompt, AnalysisRun } from './lib/api'
import './styles/app.css'

type View = 'Dashboard' | 'Websites' | 'Scans' | 'Knowledge Graph' | 'Analyse' | 'API Docs' | 'MCP Server' | 'Users' | 'Settings'
type SettingsTab = 'providers' | 'google' | 'crawl' | 'prompts'

const nav: { label: View; icon: React.ComponentType<{ size?: number }> }[] = [
  { label: 'Dashboard', icon: Activity },
  { label: 'Websites', icon: Globe2 },
  { label: 'Scans', icon: Play },
  { label: 'Knowledge Graph', icon: Network },
  { label: 'Analyse', icon: ClipboardList },
  { label: 'API Docs', icon: BookOpen },
  { label: 'MCP Server', icon: Cable },
  { label: 'Users', icon: Users },
  { label: 'Settings', icon: Settings }
]

const buildCommit = import.meta.env.VITE_COMMIT_ID ?? 'dev'
const buildTimeIso = import.meta.env.VITE_BUILD_TIME_ISO ?? ''
const selectedWebsiteStoragePrefix = 'companycrawler-selected-website'
const supportedEmbeddingModels = new Set(['text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002'])

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
  default_agent_provider: 'openai',
  default_agent_model: 'gpt-5.4-mini',
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
  const [analysisPrompts, setAnalysisPrompts] = useState<AnalysisPrompt[]>([])
  const [analyses, setAnalyses] = useState<AnalysisRun[]>([])
  const [activeAnalysis, setActiveAnalysis] = useState<AnalysisRun | null>(null)
  const [selectedWebsite, setSelectedWebsite] = useState<Website | null>(null)
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null)
  const [scan, setScan] = useState<Scan | null>(null)
  const [formUrl, setFormUrl] = useState('https://example.com')
  const [formCompany, setFormCompany] = useState('Example')
  const [formLogoUrl, setFormLogoUrl] = useState('')
  const [editWebsiteId, setEditWebsiteId] = useState<number | null>(null)
  const [websiteDialogMode, setWebsiteDialogMode] = useState<'create' | 'edit' | null>(null)
  const [editUserId, setEditUserId] = useState<number | null>(null)
  const [userDialogMode, setUserDialogMode] = useState<'create' | 'edit' | null>(null)
  const [userFormEmail, setUserFormEmail] = useState('')
  const [userFormName, setUserFormName] = useState('')
  const [userFormRole, setUserFormRole] = useState('user')
  const [userFormActive, setUserFormActive] = useState(true)
  const [message, setMessage] = useState('Klaar om een website te scannen.')
  const [theme, setTheme] = useState<'light' | 'dark'>(() => localStorage.getItem('companycrawler-theme') === 'dark' ? 'dark' : 'light')

  const activeModel = useMemo(() => models.find((model) => model.purpose === 'summary') ?? models[0], [models])

  function selectedWebsiteStorageKey(activeUser: User | null) {
    return activeUser ? `${selectedWebsiteStoragePrefix}-${activeUser.id}` : selectedWebsiteStoragePrefix
  }

  function rememberSelectedWebsite(website: Website | null, activeUser: User | null = user) {
    const key = selectedWebsiteStorageKey(activeUser)
    if (website) {
      localStorage.setItem(key, String(website.id))
      return
    }
    localStorage.removeItem(key)
  }

  function getRememberedWebsiteId(activeUser: User | null = user) {
    const value = localStorage.getItem(selectedWebsiteStorageKey(activeUser))
    const id = value ? Number(value) : 0
    return Number.isFinite(id) && id > 0 ? id : null
  }

  async function load(activeUser: User | null = user) {
    const [websiteRows, modelRows, userRows, providerSettings, promptRows] = await Promise.all([
      api.websites(),
      api.models(),
      api.users().catch(() => []),
      api.providerSettings(),
      api.analysisPrompts()
    ])
    setWebsites(websiteRows)
    setModels(modelRows)
    setUsers(userRows)
    setSettings(providerSettings)
    setAnalysisPrompts(promptRows)
    const rememberedWebsiteId = getRememberedWebsiteId(activeUser)
    const website =
      (selectedWebsite ? websiteRows.find((item) => item.id === selectedWebsite.id) : null) ??
      (rememberedWebsiteId ? websiteRows.find((item) => item.id === rememberedWebsiteId) : null) ??
      websiteRows[0] ??
      null
    await selectWebsite(website, false, activeUser)
  }

  async function selectWebsite(website: Website | null, announce = true, activeUser: User | null = user) {
    setSelectedWebsite(website)
    rememberSelectedWebsite(website, activeUser)
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
    const analysisRows = await api.analyses(website.id).catch(() => [])
    setAnalyses(analysisRows)
    setActiveAnalysis(analysisRows[0] ?? null)
    if (announce) setMessage(`${website.company_name} is actief geselecteerd.`)
  }

  useEffect(() => {
    api.providerSettings()
      .then(async (providerSettings) => {
        setSettings(providerSettings)
        if (!providerSettings.google_auth_enabled) {
          setMessage('Google login is nog niet geconfigureerd.')
          return undefined
        }
        const loggedIn = await api.session().catch(() => null)
        if (loggedIn) {
          setUser(loggedIn)
          if (loggedIn.role === 'guest') return undefined
          await load(loggedIn)
        }
        return undefined
      })
      .catch((error) => setMessage(error.message))
  }, [])

  useEffect(() => {
    if (!scan || ['completed', 'failed', 'stopped'].includes(scan.status)) return
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

  useEffect(() => {
    if (!activeAnalysis || ['completed', 'failed'].includes(activeAnalysis.status)) return
    const timer = window.setInterval(async () => {
      const fresh = await api.analysis(activeAnalysis.id)
      setActiveAnalysis(fresh)
      setAnalyses((rows) => rows.map((analysis) => (analysis.id === fresh.id ? fresh : analysis)))
      if (fresh.status === 'completed') setMessage('Analyse afgerond.')
      if (fresh.status === 'failed') setMessage(`Analyse mislukt: ${fresh.error}`)
    }, 1200)
    return () => window.clearInterval(timer)
  }, [activeAnalysis?.id, activeAnalysis?.status])

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
      setWebsiteDialogMode(null)
      setMessage('Website bijgewerkt.')
      return updated
    }
    const created = await api.createWebsite(formUrl, formCompany, formLogoUrl)
    setWebsites((rows) => [created, ...rows])
    await selectWebsite(created)
    setWebsiteDialogMode(null)
    setMessage('Website aangemaakt en actief geselecteerd.')
    return created
  }

  async function startScan() {
    if (scan?.status === 'paused') {
      const resumed = await api.resumeScan(scan.id)
      setScan(resumed)
      setMessage('Scan hervat. Voortgang wordt realtime bijgewerkt.')
      setView('Dashboard')
      return
    }
    const website = selectedWebsite ?? await saveWebsite()
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

  async function pauseScan() {
    if (!scan || !['queued', 'running'].includes(scan.status)) return
    const paused = await api.pauseScan(scan.id)
    setScan(paused)
    setMessage('Scan gepauzeerd.')
  }

  async function stopScan() {
    if (!scan || !['queued', 'running', 'paused'].includes(scan.status)) return
    const stopped = await api.stopScan(scan.id)
    setScan(stopped)
    setMessage('Scan gestopt.')
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
    await resetWebsiteData(selectedWebsite)
  }

  async function resetWebsiteData(website: Website) {
    if (!window.confirm(`Alle scan- en analysedata van ${website.company_name} verwijderen? De website zelf blijft bestaan.`)) return
    await api.resetWebsite(website.id)
    if (selectedWebsite?.id === website.id) {
      setDocuments([])
      setSelectedDocument(null)
      setAnalyses([])
      setActiveAnalysis(null)
      setScan(null)
    }
    setMessage('Alle scan- en analysedata voor deze website is verwijderd.')
  }

  function openNewWebsiteDialog() {
    setEditWebsiteId(null)
    setFormUrl('https://example.com')
    setFormCompany('Example')
    setFormLogoUrl('')
    setWebsiteDialogMode('create')
  }

  function openEditWebsiteDialog(website: Website) {
    setEditWebsiteId(website.id)
    setFormUrl(website.url)
    setFormCompany(website.company_name)
    setFormLogoUrl(website.logo_url ?? '')
    setWebsiteDialogMode('edit')
  }

  function closeWebsiteDialog() {
    setWebsiteDialogMode(null)
    setEditWebsiteId(null)
    if (selectedWebsite) {
      setFormUrl(selectedWebsite.url)
      setFormCompany(selectedWebsite.company_name)
      setFormLogoUrl(selectedWebsite.logo_url ?? '')
    }
  }

  function openNewUserDialog() {
    setEditUserId(null)
    setUserFormEmail('')
    setUserFormName('')
    setUserFormRole('user')
    setUserFormActive(true)
    setUserDialogMode('create')
  }

  function openEditUserDialog(item: User) {
    setEditUserId(item.id)
    setUserFormEmail(item.email)
    setUserFormName(item.name ?? '')
    setUserFormRole(item.role)
    setUserFormActive(item.is_active)
    setUserDialogMode('edit')
  }

  function closeUserDialog() {
    setUserDialogMode(null)
    setEditUserId(null)
  }

  async function saveUser() {
    const payload = { email: userFormEmail, name: userFormName, role: userFormRole, is_active: userFormActive }
    if (editUserId) {
      const updated = await api.updateUser(editUserId, payload)
      setUsers((rows) => rows.map((item) => (item.id === updated.id ? updated : item)))
      closeUserDialog()
      setMessage('User bijgewerkt.')
      return
    }
    const created = await api.createUser(payload)
    setUsers((rows) => [...rows, created])
    closeUserDialog()
    setMessage('User aangemaakt.')
  }

  async function deleteUser(item: User) {
    if (!window.confirm(`${item.email} verwijderen?`)) return
    await api.deleteUser(item.id)
    setUsers((rows) => rows.filter((userItem) => userItem.id !== item.id))
    setMessage('User verwijderd.')
  }

  async function startAnalysis() {
    if (!selectedWebsite) return
    setMessage('Analyse-agent jobs worden uitgevoerd...')
    setView('Analyse')
    const created = await api.startAnalysis(selectedWebsite.id)
    setActiveAnalysis(created)
    const rows = await api.analyses(selectedWebsite.id)
    setAnalyses(rows)
    setMessage(created.status === 'completed' ? 'Analyse afgerond.' : `Analyse ${created.status}.`)
  }

  async function saveAnalysisPrompt(promptId: string, promptText: string) {
    const saved = await api.saveAnalysisPrompt(promptId, promptText)
    setAnalysisPrompts((rows) => rows.map((item) => (item.prompt_id === saved.prompt_id ? saved : item)))
    setMessage('Analyseprompt opgeslagen.')
  }

  async function deleteAnalysisJobResult(jobResultId: number) {
    const analysisId = activeAnalysis?.id
    if (!analysisId || !activeAnalysis.jobs.some((job) => job.id === jobResultId) || !window.confirm('Dit jobresultaat verwijderen?')) return
    await api.deleteAnalysisJobResult(jobResultId)
    const updateRun = (analysis: AnalysisRun): AnalysisRun => ({
      ...analysis,
      jobs: analysis.jobs.filter((job) => job.id !== jobResultId)
    })
    setAnalyses((rows) => rows.map((analysis) => (analysis.id === analysisId ? updateRun(analysis) : analysis)))
    setActiveAnalysis((analysis) => (analysis && analysis.id === analysisId ? updateRun(analysis) : analysis))
    setMessage('Jobresultaat verwijderd.')
  }

  async function deleteAnalysis(analysisId: number) {
    const analysis = analyses.find((item) => item.id === analysisId)
    if (!analysis || ['queued', 'running'].includes(analysis.status) || !window.confirm(`Analyse #${analysis.id} en alle jobs/resultaten verwijderen?`)) return
    await api.deleteAnalysis(analysisId)
    const remaining = analyses.filter((item) => item.id !== analysisId)
    setAnalyses(remaining)
    setActiveAnalysis((current) => (current?.id === analysisId ? (remaining[0] ?? null) : current))
    setMessage('Analyse en alle jobresultaten verwijderd.')
  }

  function toggleTheme() {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark'
      localStorage.setItem('companycrawler-theme', next)
      return next
    })
  }

  if (!user) {
    return (
      <main className="guest-shell">
        <BuildInfo />
        <section className="guest-panel">
          <div className="guest-logo"><SmawaMark theme="light" /></div>
          <ShieldCheck size={26} />
          <h1>{settings.google_auth_enabled ? 'Inloggen met Google' : 'Google login niet geconfigureerd'}</h1>
          <p>{settings.google_auth_enabled ? 'Gebruik je Google account om toegang tot companycrawler aan te vragen.' : 'Configureer GOOGLE_CLIENT_ID en GOOGLE_CLIENT_SECRET in de omgeving om de eerste Google gebruiker admin te maken.'}</p>
          {settings.google_auth_enabled && <a className="google-login-button" href="/api/auth/google/start">Inloggen met Google</a>}
          <GoogleOriginDiagnostics settings={settings} />
        </section>
      </main>
    )
  }

  if (user?.role === 'guest') {
    return (
      <main className="guest-shell">
        <BuildInfo />
        <section className="guest-panel">
          <div className="guest-logo"><SmawaMark theme="light" /></div>
          <ShieldCheck size={26} />
          <h1>Je account wacht op goedkeuring</h1>
          <p>Je Google login is geregistreerd. Een beheerder moet je nog de rol gebruiker of beheerder geven.</p>
        </section>
      </main>
    )
  }

  return (
    <main className={`app-shell theme-${theme}`}>
      <BuildInfo />
      <aside className="sidebar">
        <div className="brand">
          <SmawaMark theme={theme} />
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
              <h1>{selectedWebsite ? `${selectedWebsite.company_name} - ${selectedWebsite.url}` : 'Geen actieve website geselecteerd.'}</h1>
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
            startScan={startScan}
            pauseScan={pauseScan}
            stopScan={stopScan}
            resetSelected={resetSelected}
          />
        )}

        {view === 'Websites' && (
          <WebsitesView
            company={formCompany}
            closeWebsiteDialog={closeWebsiteDialog}
            deleteWebsite={deleteWebsite}
            detectName={detectName}
            editWebsiteId={editWebsiteId}
            saveWebsite={saveWebsite}
            selectedWebsite={selectedWebsite}
            selectWebsite={selectWebsite}
            openEditWebsiteDialog={openEditWebsiteDialog}
            openNewWebsiteDialog={openNewWebsiteDialog}
            resetWebsiteData={resetWebsiteData}
            setCompany={setFormCompany}
            setLogoUrl={setFormLogoUrl}
            setUrl={setFormUrl}
            logoUrl={formLogoUrl}
            url={formUrl}
            websiteDialogMode={websiteDialogMode}
            websites={websites}
          />
        )}

        {view === 'Scans' && <ScansView activeModel={activeModel} message={message} scan={scan} startScan={startScan} pauseScan={pauseScan} stopScan={stopScan} />}
        {view === 'Knowledge Graph' && <KnowledgeView documents={documents} selectedDocument={selectedDocument} selectedWebsite={selectedWebsite} setSelectedDocument={setSelectedDocument} />}
        {view === 'Analyse' && (
          <AnalysisView
            analyses={analyses}
            activeAnalysis={activeAnalysis}
            deleteAnalysis={deleteAnalysis}
            deleteAnalysisJobResult={deleteAnalysisJobResult}
            selectedWebsite={selectedWebsite}
            setActiveAnalysis={setActiveAnalysis}
            startAnalysis={startAnalysis}
          />
        )}
        {view === 'API Docs' && <DocsView />}
        {view === 'MCP Server' && <McpView />}
        {view === 'Users' && (
          <UsersView
            closeUserDialog={closeUserDialog}
            deleteUser={deleteUser}
            editUserId={editUserId}
            email={userFormEmail}
            isActive={userFormActive}
            name={userFormName}
            openEditUserDialog={openEditUserDialog}
            openNewUserDialog={openNewUserDialog}
            role={userFormRole}
            saveUser={saveUser}
            setEmail={setUserFormEmail}
            setIsActive={setUserFormActive}
            setName={setUserFormName}
            setRole={setUserFormRole}
            userDialogMode={userDialogMode}
            users={users}
          />
        )}
        {view === 'Settings' && (
          <SettingsView
            key={`${settings.google_client_id}:${settings.app_url_origin}:${settings.default_summary_model}:${settings.default_embedding_model}:${settings.default_agent_model}`}
            settings={settings}
            models={models}
            prompts={analysisPrompts}
            setSettings={setSettings}
            saveAnalysisPrompt={saveAnalysisPrompt}
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
  startScan: () => void
  pauseScan: () => void
  stopScan: () => void
  resetSelected: () => void
}) {
  return (
    <section className="dashboard-layout">
      <ProgressPanel
        scan={props.scan}
        documents={props.documents}
        message={props.message}
        startScan={props.startScan}
        pauseScan={props.pauseScan}
        stopScan={props.stopScan}
        resetSelected={props.resetSelected}
        selectedWebsite={props.selectedWebsite}
      />
      <TreePanel documents={props.documents} selectedDocument={props.selectedDocument} setSelectedDocument={props.setSelectedDocument} />
      <Inspector document={props.selectedDocument} website={props.selectedWebsite} />
    </section>
  )
}

function BuildInfo() {
  return <div className="build-info">commit {buildCommit} · {formatBuildTime(buildTimeIso)}</div>
}

function formatBuildTime(value: string) {
  if (!value) return 'local'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function SmawaMark({ theme }: { theme: 'light' | 'dark' }) {
  return <img className="smawa-mark" src={theme === 'dark' ? smawaLogoDark : smawaLogoLight} alt="Smawa" />
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

function formatElapsed(start: string | null, end: string | null, now: number) {
  if (!start) return '0m 00s'
  const started = new Date(start).getTime()
  const ended = end ? new Date(end).getTime() : now
  if (Number.isNaN(started) || Number.isNaN(ended)) return '0m 00s'
  const totalSeconds = Math.max(0, Math.floor((ended - started) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

function formatMb(value: number) {
  return `${value.toFixed(2)} MB`
}

function ProgressPanel({
  scan,
  documents,
  message,
  startScan,
  pauseScan,
  stopScan,
  resetSelected,
  selectedWebsite,
  activeModel
}: {
  scan: Scan | null
  documents: DocumentItem[]
  message: string
  startScan: () => void
  pauseScan: () => void
  stopScan: () => void
  resetSelected?: () => void
  selectedWebsite?: Website | null
  activeModel?: ModelConfig
}) {
  const statusText = scan?.status === 'failed' ? scan.error || scan.message : scan?.message ?? message
  const elapsedSeconds = scan ? scan.duration_seconds || secondsBetween(scan.started_at ?? scan.created_at, scan.completed_at) : 0
  const canPause = scan ? ['queued', 'running'].includes(scan.status) : false
  const canStop = scan ? ['queued', 'running', 'paused'].includes(scan.status) : false
  return (
    <div className={scan?.status === 'running' ? 'panel progress-panel scanning' : 'panel progress-panel'}>
      <div className="panel-title"><Activity size={18} /> Realtime scan voortgang</div>
      <div className="progress-ring">{scan?.progress ?? 0}%</div>
      <div className="status-line">{scan?.status ?? 'idle'} · {statusText}</div>
      {scan?.error && <pre className="scan-error">{scan.error}</pre>}
      <div className="meter"><span style={{ width: `${scan?.progress ?? 0}%` }} /></div>
      <dl>
        {activeModel && <><dt>Model</dt><dd>{activeModel.provider} · {activeModel.model}</dd></>}
        <dt>Items gevonden</dt><dd>{scan?.items_found ?? documents.length}</dd>
        <dt>Items verwerkt</dt><dd>{scan?.items_processed ?? documents.length}</dd>
        <dt>Vectorstatus</dt><dd>{documents.filter((doc) => doc.vector_status === 'ready').length}/{documents.length} klaar</dd>
        <dt>Looptijd</dt><dd>{formatDuration(elapsedSeconds)}</dd>
        <dt>Normale DB</dt><dd>{formatMb(scan?.normal_db_size_mb ?? 0)}</dd>
        <dt>Vector DB</dt><dd>{formatMb(scan?.vector_db_size_mb ?? 0)}</dd>
        <dt>Parallel</dt><dd>{scan?.scan_max_parallel_items ?? '-'} taken</dd>
      </dl>
      <div className="scan-control-row">
        <button className="primary" onClick={startScan}><Play size={17} /> Start</button>
        <button className="secondary" onClick={pauseScan} disabled={!canPause}><Pause size={17} /> Pauze</button>
        <button className="danger" onClick={stopScan} disabled={!canStop}><Square size={16} /> Stop</button>
        {resetSelected && <button className="secondary" onClick={resetSelected} disabled={!selectedWebsite}><RefreshCw size={16} /> Reset</button>}
      </div>
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
  closeWebsiteDialog: () => void
  deleteWebsite: (website: Website) => void
  detectName: () => void
  editWebsiteId: number | null
  logoUrl: string
  openEditWebsiteDialog: (website: Website) => void
  openNewWebsiteDialog: () => void
  resetWebsiteData: (website: Website) => void
  saveWebsite: () => void
  selectedWebsite: Website | null
  selectWebsite: (website: Website) => void
  setCompany: (value: string) => void
  setLogoUrl: (value: string) => void
  setUrl: (value: string) => void
  url: string
  websiteDialogMode: 'create' | 'edit' | null
  websites: Website[]
}) {
  return (
    <section className="panel websites-panel wide">
      <div className="panel-heading-row">
        <div className="panel-title"><Globe2 size={18} /> Websites</div>
        <button className="primary" onClick={props.openNewWebsiteDialog}><Plus size={17} /> Nieuwe website</button>
      </div>
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
                <button title="Bewerken" onClick={() => props.openEditWebsiteDialog(website)}><Pencil size={16} /></button>
                <button className="danger-icon" title="Scan- en analysedata resetten" onClick={() => props.resetWebsiteData(website)}><RefreshCw size={16} /></button>
                <button title="Verwijderen" onClick={() => props.deleteWebsite(website)}><Trash2 size={16} /></button>
              </div>
            </div>
          ))}
          {props.websites.length === 0 && <p className="empty">Nog geen websites. Maak je eerste website aan.</p>}
      </div>

      {props.websiteDialogMode && (
        <div className="modal-backdrop" role="presentation" onMouseDown={props.closeWebsiteDialog}>
          <div className="modal-panel website-modal" role="dialog" aria-modal="true" aria-labelledby="website-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading-row">
              <div className="panel-title" id="website-dialog-title"><Save size={18} /> {props.editWebsiteId ? 'Website bewerken' : 'Nieuwe website'}</div>
              <button className="icon-button" onClick={props.closeWebsiteDialog} title="Sluiten"><X size={17} /></button>
            </div>
            <label>Website URL</label>
            <div className="input-row">
              <input value={props.url} onChange={(event) => props.setUrl(event.target.value)} autoFocus />
              <button className="icon-button" onClick={props.detectName} title="Detecteer bedrijfsnaam"><Search size={17} /></button>
            </div>
            <label>Bedrijfsnaam</label>
            <input value={props.company} onChange={(event) => props.setCompany(event.target.value)} />
            <label>Logo URL</label>
            <div className="input-row">
              <input value={props.logoUrl} onChange={(event) => props.setLogoUrl(event.target.value)} placeholder="Automatisch gevonden of handmatig invullen" />
              <span className="logo-preview">{props.logoUrl ? <img src={props.logoUrl} alt="" /> : null}</span>
            </div>
            <div className="button-row modal-actions">
              <button className="secondary" onClick={props.closeWebsiteDialog}>Annuleren</button>
              <button className="primary" onClick={props.saveWebsite}><Save size={17} /> Opslaan</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function ScansView({
  activeModel,
  message,
  scan,
  startScan,
  pauseScan,
  stopScan
}: {
  activeModel?: ModelConfig
  message: string
  scan: Scan | null
  startScan: () => void
  pauseScan: () => void
  stopScan: () => void
}) {
  return (
    <section className="single-panel-layout">
      <ProgressPanel
        scan={scan}
        documents={[]}
        message={message}
        startScan={startScan}
        pauseScan={pauseScan}
        stopScan={stopScan}
        activeModel={activeModel}
      />
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
  canCollapse: boolean
  collapsed: boolean
  childCount: number
}

type MindEdge = {
  from: MindNode
  to: MindNode
}

function KnowledgeView(props: { documents: DocumentItem[]; selectedDocument: DocumentItem | null; selectedWebsite: Website | null; setSelectedDocument: (doc: DocumentItem) => void }) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null)
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<Set<string>>(() => new Set())
  const [viewport, setViewport] = useState({ x: 0, y: 0, scale: 0.88 })
  const dragRef = useRef<{ startX: number; startY: number; baseX: number; baseY: number } | null>(null)
  const graph = useMemo(() => buildMindmap(props.documents, props.selectedWebsite, collapsedNodeIds), [props.documents, props.selectedWebsite, collapsedNodeIds])

  const toggleNode = (node: MindNode) => {
    if (node.document) {
      props.setSelectedDocument(node.document)
      return
    }
    if (!node.canCollapse) return
    setCollapsedNodeIds((current) => {
      const next = new Set(current)
      if (next.has(node.id)) next.delete(node.id)
      else next.add(node.id)
      return next
    })
  }

  const setScale = (nextScale: number) => {
    setViewport((current) => ({ ...current, scale: Math.min(1.35, Math.max(0.45, nextScale)) }))
  }

  const resetExplorerView = () => {
    setViewport({ x: 0, y: 0, scale: 0.88 })
  }

  const collapseAll = () => {
    setCollapsedNodeIds(new Set(graph.collapsibleIds))
    resetExplorerView()
  }

  const expandAll = () => {
    setCollapsedNodeIds(new Set())
    resetExplorerView()
  }

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button')) return
    dragRef.current = { startX: event.clientX, startY: event.clientY, baseX: viewport.x, baseY: viewport.y }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    const drag = dragRef.current
    setViewport((current) => ({
      ...current,
      x: drag.baseX + event.clientX - drag.startX,
      y: drag.baseY + event.clientY - drag.startY
    }))
  }

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault()
    setScale(viewport.scale + (event.deltaY > 0 ? -0.06 : 0.06))
  }

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
        <div className="mindmap-header">
          <div className="panel-title"><Network size={18} /> Website explorer</div>
          <div className="mindmap-toolbar" aria-label="Explorer controls">
            <button className="icon-button" onClick={() => setScale(viewport.scale + 0.1)} title="Inzoomen" aria-label="Inzoomen"><Plus size={16} /></button>
            <button className="icon-button" onClick={() => setScale(viewport.scale - 0.1)} title="Uitzoomen" aria-label="Uitzoomen"><Minus size={16} /></button>
            <button className="icon-button" onClick={resetExplorerView} title="Weergave resetten" aria-label="Weergave resetten"><Maximize2 size={16} /></button>
            <button className="secondary compact" onClick={expandAll}>Alles open</button>
            <button className="secondary compact" onClick={collapseAll}>Alles dicht</button>
          </div>
        </div>
        <div
          className="mindmap-viewport"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onWheel={handleWheel}
        >
          <div
            className="mindmap-canvas"
            style={{
              width: graph.width,
              height: graph.height,
              transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`
            }}
          >
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
                  node.collapsed ? 'collapsed' : '',
                  node.document && props.selectedDocument?.id === node.document.id ? 'selected' : ''
                ].filter(Boolean).join(' ')}
                key={node.id}
                style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
                onClick={() => toggleNode(node)}
                disabled={!node.document && !node.canCollapse}
                title={node.document?.source_url || node.title}
              >
                <span className="mind-node-icon">
                  {node.canCollapse ? (node.collapsed ? <ChevronRight size={15} /> : <ChevronDown size={15} />) : <FileText size={15} />}
                </span>
                <span className="mind-node-copy">
                  <strong>{node.title}</strong>
                  <small>{node.subtitle}</small>
                </span>
              </button>
            ))}
          </div>
          <div className="mindmap-hint"><Move size={14} /> Slepen om te bewegen, scrollen om te zoomen</div>
        </div>
      </div>
      <Inspector document={detail?.id === props.selectedDocument?.id ? detail : props.selectedDocument} website={props.selectedWebsite} />
    </section>
  )
}

function buildMindmap(documents: DocumentItem[], website: Website | null, collapsedNodeIds: Set<string>) {
  const nodeWidth = 230
  const nodeHeight = 70
  const columnGap = 72
  const rowGap = 16
  let cursorY = 22
  const nodes: MindNode[] = []
  const edges: MindEdge[] = []
  const treeRoot = buildDocumentTree(uniqueDocuments(documents))
  const collapsibleIds = ['root', ...collectCollapsibleTreeIds(treeRoot)]
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
    depth: 0,
    canCollapse: treeRoot.length > 0,
    collapsed: collapsedNodeIds.has('root'),
    childCount: treeRoot.reduce((total, child) => total + countTreeDocuments(child), 0)
  }
  nodes.push(rootNode)

  function placeTreeNode(treeNode: DocumentTreeNode, parent: MindNode, depth: number): MindNode {
    maxDepth = Math.max(maxDepth, depth)
    const document = treeNode.document
    const id = document ? `doc-${document.id}` : `group-${treeNode.id}`
    const childCount = countTreeDocuments(treeNode)
    const canCollapse = !document && treeNode.children.length > 0
    const collapsed = canCollapse && collapsedNodeIds.has(id)
    const mindNode: MindNode = {
      id,
      title: compactTitle(document ? (document.title || treeNode.label) : treeNode.label, 54),
      subtitle: document ? compactTitle(document.display_summary || document.summary || document.source_url, 72) : `${childCount} item${childCount === 1 ? '' : 's'}${collapsed ? ' verborgen' : ''}`,
      x: 24 + depth * (nodeWidth + columnGap),
      y: cursorY,
      width: nodeWidth,
      height: nodeHeight,
      document,
      kind: document ? 'document' : 'group',
      depth,
      canCollapse,
      collapsed,
      childCount
    }
    cursorY += nodeHeight + rowGap
    nodes.push(mindNode)
    edges.push({ from: parent, to: mindNode })
    if (!collapsed) {
      for (const child of treeNode.children) {
        placeTreeNode(child, mindNode, depth + 1)
      }
    }
    return mindNode
  }

  if (!rootNode.collapsed) {
    for (const child of treeRoot) {
      placeTreeNode(child, rootNode, 1)
    }
  }

  const height = Math.max(360, cursorY + 20)
  rootNode.y = Math.max(22, height / 2 - nodeHeight / 2)
  return { nodes, edges, width: Math.max(840, 48 + (maxDepth + 1) * nodeWidth + maxDepth * columnGap), height, collapsibleIds }
}

function collectCollapsibleTreeIds(nodes: DocumentTreeNode[]) {
  const ids: string[] = []
  function walk(node: DocumentTreeNode) {
    if (!node.document && node.children.length > 0) ids.push(`group-${node.id}`)
    node.children.forEach(walk)
  }
  nodes.forEach(walk)
  return ids
}

function uniqueDocuments(documents: DocumentItem[]) {
  const byKey = new Map<string, DocumentItem>()
  for (const document of documents) {
    const key = document.text_hash ? `hash:${document.text_hash}` : `url:${canonicalFrontendUrl(document.source_url)}`
    const existing = byKey.get(key)
    if (!existing || (existing.vector_status === 'duplicate' && document.vector_status !== 'duplicate')) {
      byKey.set(key, document)
    }
  }
  return Array.from(byKey.values())
}

function canonicalFrontendUrl(value: string): string {
  try {
    const parsed = new URL(value)
    if (parsed.protocol === 'mailto:') {
      return canonicalMailtoBacklink(value)
    }
    parsed.hash = ''
    parsed.hostname = parsed.hostname.replace(/^www\./, '').toLowerCase()
    if (parsed.pathname === '/') parsed.pathname = ''
    return parsed.toString()
  } catch {
    return value
  }
}

function canonicalMailtoBacklink(value: string): string {
  const match = value.match(/^mailto:[^@/]+@([^/?#]+)(\/[^?#]*)/i)
  if (!match) return value
  return canonicalFrontendUrl(`https://${match[1]}${match[2]}`)
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

function AnalysisView({
  analyses,
  activeAnalysis,
  deleteAnalysis,
  deleteAnalysisJobResult,
  selectedWebsite,
  setActiveAnalysis,
  startAnalysis
}: {
  analyses: AnalysisRun[]
  activeAnalysis: AnalysisRun | null
  deleteAnalysis: (analysisId: number) => void
  deleteAnalysisJobResult: (jobResultId: number) => void
  selectedWebsite: Website | null
  setActiveAnalysis: (analysis: AnalysisRun) => void
  startAnalysis: () => void
}) {
  const [selectedPromptId, setSelectedPromptId] = useState<string>('')
  const [now, setNow] = useState(() => Date.now())
  const selectedJob = activeAnalysis?.jobs.find((job) => job.prompt_id === selectedPromptId) ?? activeAnalysis?.jobs[0] ?? null
  const runningJob = activeAnalysis?.jobs.find((job) => job.status === 'running') ?? null
  const currentJobLabel = runningJob
    ? runningJob.prompt_id.replace('job_', '').replace(/_/g, ' ')
    : activeAnalysis?.status === 'completed'
      ? 'afgerond'
      : activeAnalysis?.status === 'failed'
        ? 'mislukt'
        : activeAnalysis?.status === 'queued'
          ? 'wachten op eerste job'
          : 'tussen jobs'
  const elapsedLabel = activeAnalysis ? formatElapsed(activeAnalysis.started_at ?? activeAnalysis.created_at, activeAnalysis.completed_at, now) : '0m 00s'

  useEffect(() => {
    if (!activeAnalysis || activeAnalysis.completed_at) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [activeAnalysis?.id, activeAnalysis?.completed_at])

  return (
    <section className="analysis-layout">
      <div className="panel analysis-list-panel">
        <div className="panel-title"><ClipboardList size={18} /> Analyse-agent</div>
        <p className="body-text">{selectedWebsite ? `${selectedWebsite.company_name} wordt geanalyseerd met 9 vaste agent jobs.` : 'Selecteer eerst een website.'}</p>
        <button className="primary" onClick={startAnalysis} disabled={!selectedWebsite}><Sparkles size={17} /> Analyse starten</button>
        {activeAnalysis && (
          <div className="analysis-live-stats">
            <span>Status: {activeAnalysis.status}</span>
            <span>Bezig met: {currentJobLabel}</span>
            <span>Duur: {elapsedLabel}</span>
          </div>
        )}
        <div className="table-list compact-list">
          {analyses.map((analysis) => (
            <div
              className={activeAnalysis?.id === analysis.id ? 'table-row analysis-run-row selected' : 'table-row analysis-run-row'}
              key={analysis.id}
              onClick={() => setActiveAnalysis(analysis)}
            >
              <button className="analysis-run-main" onClick={() => setActiveAnalysis(analysis)}>
                <strong>Analyse #{analysis.id}</strong>
                <span>{analysis.status}</span>
                <small>{new Date(analysis.created_at).toLocaleString()}</small>
              </button>
              <button
                className="icon-button danger"
                title="Analyse en alle jobs verwijderen"
                disabled={analysis.status === 'queued' || analysis.status === 'running'}
                onClick={(event) => {
                  event.stopPropagation()
                  deleteAnalysis(analysis.id)
                }}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      </div>
      <div className="panel analysis-detail-panel wide">
        <div className="panel-title"><Network size={18} /> Jobresultaten</div>
        {!activeAnalysis && <p className="body-text">Nog geen analyse voor deze website.</p>}
        {activeAnalysis && (
          <>
            <div className="analysis-vars">
              <span>{activeAnalysis.extracted_variables.Bedrijfsnaam || 'Bedrijf onbekend'}</span>
              <span>{activeAnalysis.extracted_variables.Bedrijfsplaats || 'Plaats onbekend'}</span>
              <span>{activeAnalysis.extracted_variables.Regio || 'Regio onbekend'}</span>
            </div>
            <div className="job-tabs">
              {activeAnalysis.jobs.map((job) => (
                <button className={selectedJob?.prompt_id === job.prompt_id ? 'active' : ''} key={job.prompt_id} onClick={() => setSelectedPromptId(job.prompt_id)}>
                  {job.prompt_id.replace('job_', '').replace(/_/g, ' ')}
                </button>
              ))}
            </div>
            {selectedJob && (
              <div className="analysis-result">
                <div className="analysis-result-header">
                  <div className="status-line">{selectedJob.status} - {selectedJob.completed_at ? new Date(selectedJob.completed_at).toLocaleString() : 'bezig'}</div>
                  <button className="danger" title="Jobresultaat verwijderen" disabled={selectedJob.status === 'queued' || selectedJob.status === 'running'} onClick={() => deleteAnalysisJobResult(selectedJob.id)}><Trash2 size={16} /></button>
                </div>
                {selectedJob.error && <pre className="scan-error">{selectedJob.error}</pre>}
                <p>{selectedJob.summary || 'Geen samenvatting beschikbaar.'}</p>
                <pre>{selectedJob.result_json ? JSON.stringify(selectedJob.result_json, null, 2) : selectedJob.result_text}</pre>
                <div className="source-list">
                  {selectedJob.sources.slice(0, 8).map((source, index) => (
                    <a href={source.url} target="_blank" key={`${source.document_id}-${index}`}>
                      {source.title || source.url || `Bron ${index + 1}`}
                    </a>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
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
      <code>POST /mcp</code>
      <code>{'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"client","version":"1.0.0"}}}'}</code>
      <code>{'{"jsonrpc":"2.0","id":2,"method":"tools/list"}'}</code>
      <code>{'{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_websites","arguments":{}}}'}</code>
      <code>POST /mcp/tools/list_websites</code>
      <code>POST /mcp/tools/start_scan</code>
      <code>POST /mcp/tools/get_scan_status</code>
      <code>POST /mcp/tools/search_company_data</code>
      <code>POST /mcp/tools/get_company_profile</code>
      <code>POST /mcp/tools/list_analysis_prompts</code>
      <code>POST /mcp/tools/run_company_analysis</code>
      <code>POST /mcp/tools/get_company_analysis</code>
      <code>POST /mcp/tools/generate_company_scenarios</code>
      <code>POST /mcp/tools/generate_poc_brief</code>
    </section>
  )
}

function UsersView(props: {
  closeUserDialog: () => void
  deleteUser: (user: User) => void
  editUserId: number | null
  email: string
  isActive: boolean
  name: string
  openEditUserDialog: (user: User) => void
  openNewUserDialog: () => void
  role: string
  saveUser: () => void
  setEmail: (value: string) => void
  setIsActive: (value: boolean) => void
  setName: (value: string) => void
  setRole: (value: string) => void
  userDialogMode: 'create' | 'edit' | null
  users: User[]
}) {
  return (
    <section className="panel wide">
      <div className="panel-heading-row">
        <div className="panel-title"><Users size={18} /> Users</div>
        <button className="primary" onClick={props.openNewUserDialog}><Plus size={17} /> Nieuwe user</button>
      </div>
      <div className="table-list user-list">
        {props.users.map((item) => (
          <div className="table-row user-management-row" key={item.id}>
            <div>
              <strong>{item.email}</strong>
              <small>{item.name || '-'}</small>
            </div>
            <span className={item.is_active ? 'status-ok compact-status' : 'status-warn compact-status'}>
              {item.is_active ? 'actief' : 'inactief'}
            </span>
            <span>{item.role}</span>
            <div className="row-actions">
              <button title="Bewerken" onClick={() => props.openEditUserDialog(item)}><Pencil size={16} /></button>
              <button title="Verwijderen" onClick={() => props.deleteUser(item)}><Trash2 size={16} /></button>
            </div>
          </div>
        ))}
        {props.users.length === 0 && <p className="empty">Nog geen users. Maak je eerste user aan.</p>}
      </div>

      {props.userDialogMode && (
        <div className="modal-backdrop" role="presentation" onMouseDown={props.closeUserDialog}>
          <div className="modal-panel user-modal" role="dialog" aria-modal="true" aria-labelledby="user-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="panel-heading-row">
              <div className="panel-title" id="user-dialog-title"><Save size={18} /> {props.editUserId ? 'User bewerken' : 'Nieuwe user'}</div>
              <button className="icon-button" onClick={props.closeUserDialog} title="Sluiten"><X size={17} /></button>
            </div>
            <label>E-mail</label>
            <input value={props.email} onChange={(event) => props.setEmail(event.target.value)} autoFocus />
            <label>Naam</label>
            <input value={props.name} onChange={(event) => props.setName(event.target.value)} />
            <div className="form-grid two-columns">
              <div>
                <label>Rol</label>
                <select value={props.role} onChange={(event) => props.setRole(event.target.value)}>
                  <option value="guest">guest</option>
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <label className="checkbox-line">
                <input type="checkbox" checked={props.isActive} onChange={(event) => props.setIsActive(event.target.checked)} />
                Actief
              </label>
            </div>
            <div className="button-row modal-actions">
              <button className="secondary" onClick={props.closeUserDialog}>Annuleren</button>
              <button className="primary" onClick={props.saveUser} disabled={!props.email.trim()}><Save size={17} /> Opslaan</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function SettingsView({
  settings,
  models,
  prompts,
  setSettings,
  saveAnalysisPrompt,
  refresh
}: {
  settings: ProviderSettings
  models: ModelConfig[]
  prompts: AnalysisPrompt[]
  setSettings: (settings: ProviderSettings) => void
  saveAnalysisPrompt: (promptId: string, promptText: string) => Promise<void>
  refresh: () => void
}) {
  const [openaiKey, setOpenaiKey] = useState('')
  const [openrouterKey, setOpenrouterKey] = useState('')
  const [googleClientId, setGoogleClientId] = useState(settings.google_client_id)
  const [googleClientSecret, setGoogleClientSecret] = useState('')
  const [summaryModel, setSummaryModel] = useState(settings.default_summary_model)
  const [summaryProvider, setSummaryProvider] = useState(settings.default_summary_provider)
  const [embeddingModel, setEmbeddingModel] = useState(settings.default_embedding_model)
  const [embeddingProvider, setEmbeddingProvider] = useState(settings.default_embedding_provider)
  const [agentModel, setAgentModel] = useState(settings.default_agent_model)
  const [agentProvider, setAgentProvider] = useState(settings.default_agent_provider)
  const [scanMaxItems, setScanMaxItems] = useState(settings.scan_max_items)
  const [scanMaxFileMb, setScanMaxFileMb] = useState(settings.scan_max_file_mb)
  const [scanMaxDepth, setScanMaxDepth] = useState(settings.scan_max_depth)
  const [scanMaxParallelItems, setScanMaxParallelItems] = useState(settings.scan_max_parallel_items)
  const [activeTab, setActiveTab] = useState<SettingsTab>('providers')

  async function save() {
    const saved = await api.saveProviderSettings({
      openai_api_key: openaiKey,
      openrouter_api_key: openrouterKey,
      google_client_id: googleClientId,
      google_client_secret: googleClientSecret,
      default_summary_provider: summaryProvider,
      default_summary_model: summaryModel,
      default_embedding_provider: embeddingProvider,
      default_embedding_model: embeddingModel,
      default_agent_provider: agentProvider,
      default_agent_model: agentModel,
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
    <section className="panel settings-panel wide">
      <div className="settings-tabs" role="tablist" aria-label="Settings onderdelen">
        <button className={activeTab === 'providers' ? 'active' : ''} onClick={() => setActiveTab('providers')} type="button">
          <KeyRound size={16} /> Provider instellingen
        </button>
        <button className={activeTab === 'google' ? 'active' : ''} onClick={() => setActiveTab('google')} type="button">
          <ShieldCheck size={16} /> Google authenticatie
        </button>
        <button className={activeTab === 'crawl' ? 'active' : ''} onClick={() => setActiveTab('crawl')} type="button">
          <Network size={16} /> Crawl instellingen
        </button>
        <button className={activeTab === 'prompts' ? 'active' : ''} onClick={() => setActiveTab('prompts')} type="button">
          <ClipboardList size={16} /> Promptbeheer
        </button>
      </div>

      {activeTab === 'providers' && (
        <div className="settings-tab-body">
          <div className="panel-title"><KeyRound size={18} /> Provider instellingen</div>
          <StatusLine ok={settings.openai_configured} label="OpenAI API key" />
          <label>Nieuwe OpenAI API key</label>
          <input type="password" value={openaiKey} onChange={(event) => setOpenaiKey(event.target.value)} placeholder={settings.openai_configured ? 'Ingesteld, laat leeg om te behouden' : 'sk-...'} />
          <StatusLine ok={settings.openrouter_configured} label="OpenRouter API key" />
          <label>Nieuwe OpenRouter API key</label>
          <input type="password" value={openrouterKey} onChange={(event) => setOpenrouterKey(event.target.value)} placeholder={settings.openrouter_configured ? 'Ingesteld, laat leeg om te behouden' : 'sk-or-...'} />
          <label>Default summary model</label>
          <ModelSelect
            models={models}
            provider={summaryProvider}
            model={summaryModel}
            filterModel={isSummaryModel}
            recommendedLabel="Aanbevolen voor samenvattingen"
            onChange={(next) => {
              setSummaryProvider(next.provider)
              setSummaryModel(next.model)
            }}
          />
          <label>Default embedding model</label>
          <ModelSelect
            models={models}
            provider={embeddingProvider}
            model={embeddingModel}
            filterModel={isSupportedEmbeddingModel}
            recommendedLabel="Aanbevolen voor embeddings"
            onChange={(next) => {
              setEmbeddingProvider(next.provider)
              setEmbeddingModel(next.model)
            }}
          />
          <label>Default agent model</label>
          <ModelSelect
            models={models}
            provider={agentProvider}
            model={agentModel}
            filterModel={(item) => ['chat', 'reasoning', 'multimodal', 'summary'].includes(item.purpose)}
            recommendedLabel="Aanbevolen voor agent-analyse"
            onChange={(next) => {
              setAgentProvider(next.provider)
              setAgentModel(next.model)
            }}
          />
          <button className="primary" onClick={save}><Save size={17} /> Instellingen opslaan</button>
        </div>
      )}

      {activeTab === 'google' && (
        <div className="settings-tab-body">
          <div className="panel-title"><ShieldCheck size={18} /> Google authenticatie</div>
          <StatusLine ok={settings.google_auth_enabled} label="Google login" />
          <label>Google Client ID</label>
          <input value={googleClientId} onChange={(event) => setGoogleClientId(event.target.value)} placeholder="Google OAuth Client ID" />
          <GoogleOriginDiagnostics settings={settings} />
          <StatusLine ok={settings.google_client_secret_configured} label="Google Client Secret" />
          <label>Google Client Secret</label>
          <input type="password" value={googleClientSecret} onChange={(event) => setGoogleClientSecret(event.target.value)} placeholder={settings.google_client_secret_configured ? 'Ingesteld, laat leeg om te behouden' : 'Vereist voor server-side redirect login'} />
          <p className="body-text">De backend wisselt de Google authorization code om voor een ID token en zet daarna een sessiecookie. Secrets worden alleen in .env opgeslagen en niet teruggetoond.</p>
          <button className="primary" onClick={save}><Save size={17} /> Instellingen opslaan</button>
        </div>
      )}

      {activeTab === 'crawl' && (
        <div className="settings-tab-body compact-settings">
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
      )}

      {activeTab === 'prompts' && (
        <div className="settings-tab-body prompt-tab-body">
          <PromptManager prompts={prompts} saveAnalysisPrompt={saveAnalysisPrompt} />
        </div>
      )}
    </section>
  )
}

function ModelSelect({
  models,
  provider,
  model,
  filterModel,
  recommendedLabel,
  onChange
}: {
  models: ModelConfig[]
  provider: string
  model: string
  filterModel: (model: ModelConfig) => boolean
  recommendedLabel: string
  onChange: (value: { provider: string; model: string }) => void
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const comboboxRef = useRef<HTMLDivElement>(null)
  const candidates = models
    .filter(filterModel)
    .sort((a, b) => Number(b.is_default) - Number(a.is_default) || a.provider.localeCompare(b.provider) || a.model.localeCompare(b.model))
  const selectedKey = `${provider}||${model}`
  const selected = candidates.find((item) => `${item.provider}||${item.model}` === selectedKey)
  const hasSelected = Boolean(selected)
  const normalizedQuery = query.trim().toLowerCase()
  const filteredCandidates = normalizedQuery
    ? candidates.filter((item) => modelSearchText(item).includes(normalizedQuery))
    : candidates
  const selectedInFiltered = filteredCandidates.some((item) => `${item.provider}||${item.model}` === selectedKey)
  const visibleCandidates = selected && !selectedInFiltered ? [selected, ...filteredCandidates] : filteredCandidates
  const selectionTitle = selected ? selected.model : model
  const selectionProvider = selected ? selected.provider : provider
  const selectionPurpose = selected ? selected.purpose : 'handmatig'

  useEffect(() => {
    if (!open) return
    function handleOutsideClick(event: MouseEvent) {
      if (!comboboxRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [open])

  function handleChange(value: string) {
    const [nextProvider, nextModel] = value.split('||')
    onChange({ provider: nextProvider || provider, model: nextModel || model })
    setOpen(false)
    setQuery('')
  }

  return (
    <div className={selected?.is_default ? 'model-select recommended-model' : 'model-select'} ref={comboboxRef}>
      <button
        className="model-combobox-button"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="model-selected-grid">
          <span className="model-provider-pill">{selectionProvider}</span>
          <strong>{selectionTitle}</strong>
          <span>{selectionPurpose}</span>
          {!hasSelected && <span className="model-manual-note">handmatig ingesteld</span>}
        </span>
        <ChevronDown size={17} aria-hidden="true" />
      </button>
      {open && (
        <div className="model-combobox-menu">
          <div className="model-select-search">
            <Search size={15} aria-hidden="true" />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') setOpen(false)
              }}
              placeholder="Zoek op provider, model, type of toepassing"
              aria-label="Zoeken in modellen"
            />
          </div>
          <div className="model-option-header" aria-hidden="true">
            <span>Provider</span>
            <span>Model</span>
            <span>Type</span>
            <span>Toepassing</span>
          </div>
          <div className="model-option-list" role="listbox">
            {!hasSelected && (
              <button className="model-option-row selected" type="button" role="option" aria-selected="true" onClick={() => setOpen(false)}>
                <span className="model-provider-pill">{provider}</span>
                <strong>{model}</strong>
                <span>handmatig</span>
                <span>Dit model staat ingesteld, maar staat niet in de gefilterde catalogus.</span>
              </button>
            )}
            {visibleCandidates.map((item) => {
              const key = `${item.provider}||${item.model}`
              return (
                <button
                  className={key === selectedKey ? 'model-option-row selected' : 'model-option-row'}
                  type="button"
                  role="option"
                  aria-selected={key === selectedKey}
                  value={key}
                  key={`${item.provider}:${item.model}`}
                  onClick={() => handleChange(key)}
                >
                  <span className="model-provider-pill">{item.provider}</span>
                  <strong>{item.model}</strong>
                  <span>{item.purpose}</span>
                  <span>{compactTitle(item.best_for, 150)}</span>
                </button>
              )
            })}
            {visibleCandidates.length === 0 && hasSelected && (
              <div className="model-option-empty">Geen passende modellen gevonden.</div>
            )}
          </div>
        </div>
      )}
      {selected && (
        <div className="model-select-meta">
          {selected.is_default && <span className="recommended-badge">{recommendedLabel}</span>}
          <small>{selected.provider} - {selected.model} - {selected.purpose}</small>
          <p>{selected.best_for}</p>
        </div>
      )}
    </div>
  )
}

function isSummaryModel(item: ModelConfig) {
  const name = `${item.model} ${item.purpose}`.toLowerCase()
  return ['chat', 'reasoning', 'summary'].includes(item.purpose)
    && !['embed', 'image', 'vision', 'audio', 'tts', 'whisper'].some((token) => name.includes(token))
}

function isSupportedEmbeddingModel(item: ModelConfig) {
  return item.provider === 'openai' && item.purpose === 'embedding' && supportedEmbeddingModels.has(item.model)
}

function modelSearchText(item: ModelConfig) {
  return `${item.provider} ${item.model} ${item.purpose} ${item.best_for}`.toLowerCase()
}

function PromptManager({ prompts, saveAnalysisPrompt }: { prompts: AnalysisPrompt[]; saveAnalysisPrompt: (promptId: string, promptText: string) => Promise<void> }) {
  const [selectedPromptId, setSelectedPromptId] = useState('')
  const selected = prompts.find((prompt) => prompt.prompt_id === selectedPromptId) ?? prompts[0]
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({})
  const promptText = selected ? promptDrafts[selected.prompt_id] ?? selected.prompt_text : ''

  async function save() {
    if (!selected) return
    await saveAnalysisPrompt(selected.prompt_id, promptText)
  }

  return (
    <div className="prompt-manager">
      <div className="panel-title"><ClipboardList size={18} /> Promptbeheer</div>
      <label>Prompt id</label>
      <select value={selected?.prompt_id ?? ''} onChange={(event) => setSelectedPromptId(event.target.value)}>
        {prompts.map((prompt) => (
          <option value={prompt.prompt_id} key={prompt.prompt_id}>{prompt.prompt_id}</option>
        ))}
      </select>
      {selected && (
        <>
          <small>{selected.title} · {selected.description}</small>
          <textarea value={promptText} onChange={(event) => setPromptDrafts((drafts) => ({ ...drafts, [selected.prompt_id]: event.target.value }))} />
          {!promptText.trim() && <p className="inline-warning">Deze prompt mag niet leeg zijn.</p>}
          <div className="prompt-meta">
            <span>{selected.is_system_prompt ? 'Systeemprompt' : 'Agent job'}</span>
            <span>Laatst gewijzigd {new Date(selected.updated_at).toLocaleString()}</span>
          </div>
          <button className="primary" onClick={save} disabled={!promptText.trim()}><Save size={17} /> Prompt opslaan</button>
        </>
      )}
    </div>
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
