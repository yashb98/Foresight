import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Cpu,
  Bell,
  TrendingUp,
  Settings,
  ShieldCheck,
  DollarSign,
  Zap,
  ChevronRight,
  Database,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/dashboard',    icon: LayoutDashboard, label: 'Overview' },
  { to: '/assets',       icon: Cpu,             label: 'Assets' },
  { to: '/alerts',       icon: Bell,            label: 'Alerts' },
  { to: '/trends',       icon: TrendingUp,      label: 'Trends' },
  { to: '/predictions',  icon: Zap,             label: 'Predictions' },
  { to: '/cost',         icon: DollarSign,      label: 'Cost Avoidance' },
  { to: '/data-sources', icon: Database,        label: 'Data Sources' },
  { to: '/rules',        icon: ShieldCheck,     label: 'Alert Rules' },
  { to: '/settings',     icon: Settings,        label: 'Settings' },
]

export function Sidebar() {
  const location = useLocation()

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-border bg-card/50 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-border/50 px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/50 shadow-lg shadow-primary/20">
          <Zap className="h-5 w-5 text-primary-foreground" />
        </div>
        <div>
          <div className="text-sm font-bold text-foreground tracking-wide">FORESIGHT</div>
          <div className="text-[10px] text-muted-foreground uppercase tracking-widest">
            Predictive Maintenance
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname === to || location.pathname.startsWith(`${to}/`)
          return (
            <NavLink
              key={to}
              to={to}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary/10 text-primary shadow-sm'
                  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
              )}
            >
              <Icon className={cn("h-4 w-4 shrink-0", isActive && "text-primary")} />
              <span className="flex-1">{label}</span>
              {isActive && <ChevronRight className="h-3.5 w-3.5 opacity-50" />}
            </NavLink>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-border/50 p-4">
        <div className="rounded-lg bg-muted/30 p-3">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-medium text-muted-foreground">System Online</span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">
            All services operational
          </p>
        </div>
      </div>
    </aside>
  )
}
