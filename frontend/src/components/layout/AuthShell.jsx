import { Gamepad2 } from "lucide-react";
import { Link } from "react-router-dom";

export function AuthShell({ children, eyebrow, title, description }) {
  return (
    <main className="grid min-h-screen grid-cols-1 md:grid-cols-[minmax(320px,0.95fr)_minmax(360px,1.05fr)]">
      <section
        className="flex min-h-[44vh] flex-col justify-between gap-12 bg-[linear-gradient(rgba(13,22,38,0.75),rgba(13,22,38,0.82)),url('https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=1600&q=80')] bg-cover bg-center p-7 text-white md:min-h-full md:p-10"
        aria-label="MyGameList"
      >
        <Link className="inline-flex w-fit items-center gap-2.5 text-lg font-extrabold text-inherit hover:no-underline" to="/">
          <Gamepad2 size={30} />
          <span>MyGameList</span>
        </Link>
        <div className="max-w-xl">
          <p className="text-xs font-extrabold uppercase text-sky-200">{eyebrow}</p>
          <h1 className="mt-3 text-[2.5rem] leading-none md:text-6xl lg:text-7xl xl:text-[5.5rem]">{title}</h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-white/80">{description}</p>
        </div>
      </section>
      <section className="grid min-h-0 place-items-center p-4 pb-9 md:min-h-screen md:p-8">{children}</section>
    </main>
  );
}
