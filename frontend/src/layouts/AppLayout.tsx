import { NavLink, Outlet } from "react-router";
import { useAuth } from "../auth/context";
import Logo from "../components/Logo";

const navigation = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/inbox", label: "Inbox" },
  { to: "/customers", label: "Customers" },
  { to: "/integrations", label: "Integrations" },
  { to: "/settings", label: "Settings" },
];

export default function AppLayout() {
  const { account, organization, signOut } = useAuth();

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col bg-ink-900 px-4 py-6 text-slate-300">
        <div className="px-2">
          <Logo inverted />
        </div>
        {organization && (
          <p className="mt-6 truncate px-2 text-xs font-medium uppercase tracking-wider text-slate-500">
            {organization.name}
          </p>
        )}
        <nav className="mt-3 space-y-1">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-white/10 text-white" : "hover:bg-white/5 hover:text-white"}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto border-t border-white/10 px-2 pt-4">
          <p className="truncate text-sm text-white">{account?.user.name ?? account?.user.email}</p>
          <p className="truncate text-xs text-slate-500">{account?.user.email}</p>
          <button onClick={() => void signOut()} className="mt-3 text-sm text-slate-400 hover:text-white">
            Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
