import { Link } from "react-router";

export default function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <div className="text-center">
        <p className="text-sm font-semibold text-brand-600">404</p>
        <h1 className="mt-2 text-2xl font-semibold">Page not found</h1>
        <p className="mt-2 text-slate-600">The page you're looking for doesn't exist.</p>
        <Link to="/" className="mt-6 inline-block text-sm font-medium text-brand-600 hover:underline">
          Back to home
        </Link>
      </div>
    </main>
  );
}
