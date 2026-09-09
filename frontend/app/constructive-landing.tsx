import { appPath } from "./paths";

export function ConstructiveLanding() {
  return (
    <main className="constructive-landing" id="top">
      <section className="constructive-landing-hero">
        <div className="constructive-landing-copy">
          <p className="constructive-overline">CONSTRUCTION MANAGEMENT SYSTEM</p>
          <h1>Управление<br />строительством</h1>
          <p className="constructive-landing-lead">Объекты, документы и материалы в одном рабочем контуре.</p>
          <p className="constructive-landing-body">Constructive помогает вести строительные объекты, контролировать документы и материалы и видеть ход работ в одном месте.</p>
          <a className="constructive-lime-button" href={appPath("/login")}>Личный кабинет</a>
          <div className="constructive-landing-facts" aria-label="Возможности Constructive">
            <span><b>•••</b>Объекты в работе</span>
            <span><b>•••</b>Организации в работе</span>
          </div>
        </div>
        <div className="constructive-landing-art" aria-label="Constructive">
          <div className="constructive-mark-frame">
            <img src={appPath("/constructive-logo.png")} alt="Constructive" />
          </div>
        </div>
      </section>
      <section className="constructive-landing-strip">
        <span>ОБЪЕКТЫ</span><span>ДОКУМЕНТЫ</span><span>МАТЕРИАЛЫ</span><span>ЖУРНАЛ РАБОТ</span>
      </section>
    </main>
  );
}
