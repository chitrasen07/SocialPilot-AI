import { Link } from "react-router";
import { useAuth } from "../auth/context";
import Logo from "../components/Logo";

const capabilities = [
  {
    title: "Understands every message",
    body: "Intent, sentiment, emotion and language — including Hindi, Hinglish, Telugu and mixed-language messages — in one structured analysis.",
  },
  {
    title: "Answers from your knowledge",
    body: "Replies are grounded in your uploaded FAQs, policies and product data. When the answer isn't there, it says so instead of guessing.",
  },
  {
    title: "Remembers your customers",
    body: "Persistent, per-customer memory of past interests, questions and preferences, with every remembered fact visible to your team.",
  },
  {
    title: "Guardrails before publishing",
    body: "Grounding, tone, safety and confidence checks run on every draft. Anything uncertain goes to a human for approval.",
  },
  {
    title: "Finds your best leads",
    body: "Purchase-intent signals become an explainable lead score, so your team knows who to talk to first and why.",
  },
  {
    title: "Shows what customers want",
    body: "Aggregated trends surface popular questions, product demand and repeated complaints across your conversations.",
  },
];

const steps = [
  "Connect your Instagram Business or Creator account through Meta's official authorization.",
  "Set your brand personality and upload the knowledge your replies should rely on.",
  "Choose manual, approval or automatic mode — and change it any time.",
];

export default function LandingPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="bg-ink-900">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Logo inverted />
          <nav className="flex items-center gap-3 text-sm font-medium">
            {isAuthenticated ? (
              <Link to="/dashboard" className="rounded-lg bg-brand-600 px-4 py-2 text-white hover:bg-brand-500">
                Open dashboard
              </Link>
            ) : (
              <>
                <Link to="/signin" className="px-3 py-2 text-slate-300 hover:text-white">
                  Sign in
                </Link>
                <Link to="/signup" className="rounded-lg bg-brand-600 px-4 py-2 text-white hover:bg-brand-500">
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
        <section className="mx-auto max-w-6xl px-6 pb-24 pt-16">
          <p className="text-sm font-medium uppercase tracking-wider text-brand-500">
            AI customer conversations for social media
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight text-white sm:text-5xl">
            Reply to every Instagram customer in their language, with answers you can trust.
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-slate-300">
            SocialPilot AI analyzes comments and messages, retrieves your verified business
            knowledge and customer history, and drafts on-brand replies — published automatically
            only when your guardrails allow it.
          </p>
        </section>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-2xl font-semibold">What SocialPilot AI does</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {capabilities.map((item) => (
              <article key={item.title} className="rounded-xl border border-slate-200 bg-white p-6">
                <h3 className="font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="border-y border-slate-200 bg-white">
          <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-2">
            <div>
              <h2 className="text-2xl font-semibold">How it works</h2>
              <ol className="mt-8 space-y-6">
                {steps.map((step, index) => (
                  <li key={step} className="flex gap-4">
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-600 text-sm font-semibold text-white">
                      {index + 1}
                    </span>
                    <p className="pt-1 text-slate-700">{step}</p>
                  </li>
                ))}
              </ol>
            </div>
            <div className="rounded-xl bg-slate-50 p-8">
              <h2 className="text-lg font-semibold">Built on official Meta APIs</h2>
              <ul className="mt-4 space-y-3 text-sm text-slate-700">
                <li>We never ask for your Instagram password.</li>
                <li>Access tokens stay on our servers and are encrypted at rest.</li>
                <li>No scraping, no browser automation, no spam tooling.</li>
                <li>Each business's data is isolated to its own organization.</li>
              </ul>
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-6 py-10 text-sm text-slate-500">
        © {new Date().getFullYear()} SocialPilot AI
      </footer>
    </div>
  );
}
