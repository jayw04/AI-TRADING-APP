import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "../routes";

export default function Sidebar() {
  return (
    <aside
      aria-label="Primary navigation"
      className="flex flex-col w-56 shrink-0 border-r border-neutral-800 bg-neutral-950"
    >
      <div className="h-12 flex items-center px-4 border-b border-neutral-800">
        <span className="text-sm font-semibold tracking-wide text-neutral-200">
          Trading Workbench
        </span>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        <ul className="space-y-0.5 px-2">
          {NAV_ITEMS.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  [
                    "block rounded px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-neutral-800 text-neutral-100"
                      : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200",
                  ].join(" ")
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
