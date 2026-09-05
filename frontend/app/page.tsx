import { ConstructiveLanding } from "./constructive-landing";
import { appPath } from "./paths";

export default function Page() {
  if (process.env.NEXT_PUBLIC_APP_PRODUCT === "constructive") return <ConstructiveLanding />;
  return <ScoutLanding />;
}

function ScoutLanding() {
  return (
    <main className="lh-site">
      <header className="lh-nav">
        <a className="lh-brand" href="#top">
          <span className="lh-brand-mark">LH</span>
          <span><strong>LEADHUNTER</strong><small>SCOUT / COMMERCIAL DEMAND</small></span>
        </a>
        <nav className="lh-nav-links">
          <a href="#how">Как работает</a>
          <a href="#pilot">Пилот</a>
          <a href={appPath("/login")}>Войти</a>
          <a className="lh-nav-cta" href={appPath("/login")}>Открыть Scout</a>
        </nav>
      </header>

      <section className="lh-hero" id="top">
        <div className="lh-hero-copy">
          <p className="lh-eyebrow">LEADHUNTER / SCOUT <span>LIVE</span></p>
          <h1>Клиент уже ищет вас.<br /><em>Scout найдёт его первым.</em></h1>
          <p className="lh-hero-lead">Scout — интеллектуальная система поиска новых возможностей для бизнеса. Он помогает находить клиентов, заказы и точки роста — вовремя и по заданным критериям.</p>
          <div className="lh-hero-actions">
            <a className="lh-button lh-button-primary" href={appPath("/login")}>Открыть рабочий кабинет</a>
            <a className="lh-text-link" href="#how">Как это работает</a>
          </div>
          <div className="lh-home-stats" aria-label="Публичные показатели Scout">
            <article className="lh-home-stat"><strong>—</strong><span>Кампании в работе</span></article>
            <article className="lh-home-stat"><strong>—</strong><span>Источники в работе</span></article>
          </div>
        </div>
        <div className="lh-hero-aside">
          <div className="lh-hero-logo">S</div>
          <strong>LEADHUNTER<br /><b>ВИДИТ РЫНОК</b></strong>
          <strong>SCOUT<br /><b>НАХОДИТ КЛИЕНТА</b></strong>
          <small>Реальные сигналы спроса, профиль и контакт в одном рабочем потоке.</small>
        </div>
      </section>

      <section className="lh-statement" id="how">
        <p className="lh-eyebrow">НЕ ПРОЦЕСС · РЕЗУЛЬТАТ</p>
        <h2>Не создаём спрос рекламой.<br /><span>Находим уже существующий.</span></h2>
        <div className="lh-statement-foot">
          <p>После входа доступны только данные вашего аккаунта и действия, разрешённые рабочей областью.</p>
          <a className="lh-button lh-button-dark" href={appPath("/login")}>Перейти к данным</a>
        </div>
      </section>

      <section className="lh-pilot" id="pilot">
        <div>
          <p className="lh-eyebrow">SCOUT / РАБОЧИЙ КАБИНЕТ</p>
          <h2>Проверяйте возможности<br /><em>в одном месте.</em></h2>
          <p>Лента, профиль поиска и обратная связь связаны с серверным API. Если данных нет, кабинет покажет это явно.</p>
        </div>
        <div className="lh-pilot-offer">
          <span>Авторизованный доступ к вашему рабочему пространству</span>
          <a className="lh-button lh-button-primary" href={appPath("/login")}>Войти в Scout</a>
        </div>
      </section>

      <footer className="lh-footer">
        <a className="lh-brand" href="#top">
          <span className="lh-brand-mark">LH</span>
          <span><strong>LEADHUNTER</strong><small>SCOUT / COMMERCIAL DEMAND</small></span>
        </a>
        <p>Scout находит существующий спрос.</p>
        <a className="lh-footer-login" href={appPath("/login")}>Войти в кабинет</a>
      </footer>
    </main>
  );
}
