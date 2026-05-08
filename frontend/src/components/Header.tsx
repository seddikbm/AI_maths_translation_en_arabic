import { Languages, MoonStar, SunMedium } from "lucide-react";

interface HeaderProps {
  theme: "light" | "dark";
  onThemeToggle: () => void;
}

export function Header({ theme, onThemeToggle }: HeaderProps) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <Languages size={20} />
        </div>
        <div>
          <p className="eyebrow">Math AI Translation</p>
          <h1>MathTrans</h1>
        </div>
      </div>
      <button type="button" className="icon-button" onClick={onThemeToggle} aria-label="Toggle theme">
        {theme === "light" ? <MoonStar size={18} /> : <SunMedium size={18} />}
      </button>
    </header>
  );
}
