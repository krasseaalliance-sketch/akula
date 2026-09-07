import type { Metadata } from "next";
import "./globals.css";
import "./core/core.css";
import "./landing.css";
import "./login/login.css";
import "./support-chat.css";
import "./cabinet-directory.css";
import "./customer-dashboard.css";
import "./constructive.css";
import "./public-dashboard.css";

export const metadata: Metadata = process.env.NEXT_PUBLIC_APP_PRODUCT === "constructive"
  ? { title: "ASmeT · Constructive", description: "Рабочее пространство Constructive" }
  : { title: "LeadHunter · Scout", description: "Scout находит существующий спрос для вашего бизнеса" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
