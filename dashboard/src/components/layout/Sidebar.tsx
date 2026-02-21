import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Cpu,
  Bell,
  TrendingUp,
  Settings,
  ShieldCheck,
  DollarSign,
  LogOut,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/button'

const navItems = [
  { to: '/dashboard',    icon: LayoutDashboard, label: 'Overview' },
  { to: '/assets',       icon: Cpu,             label: 'Assets' },
  { to: '/alerts',       icon: Bell,            label: 'Alerts' },
  { to: '/trends',       icon: TrendingUp,      label: 'Trends' },
  { to: '/predictions',  icon: Zap,             label: 'Predictions' },
  { to: '/cost',         icon: DollarSign,      label: 'Cost Avoidance' },
  { to: '/rules',        icon: ShieldCheck,     label: 'Alert Rules' },
  { to: '/settings',     icon: Settings,        label: 'Settings' },
]

export function Sidebar() {
  const logout = useAuthStore((s) => s.logout)
  const tenantId = useAuthStore((s) => s.tenantId)

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-border bg-card">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
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
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Tenant info + logout */}
      <div className="border-t border-border px-3 py-3 space-y-2">
        <div className="px-3 py-1">
          <div className="text-xs text-muted-foreground">Tenant</div>
          <div className="text-xs font-mono text-foreground truncate">{tenantId?.slice(0, 16)}…</div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground hover:text-destructive"
          onClick={logout}
        >
          <LogOut className="mr-2 h-4 w-4" />
          Sign Out
        </Button>
      </div>
    </aside>
  )
}
