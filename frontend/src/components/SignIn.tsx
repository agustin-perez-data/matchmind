import { PROVIDERS, loginUrl } from '../lib/auth'
import { Wordmark } from './Wordmark'

/** The door to the club area. Public, and loud about the fact that the demo needs no sign-in. */
export function SignIn() {
  return (
    <section className="enter mx-auto w-full max-w-3xl px-5 pb-14 pt-8 sm:px-8 sm:pt-12">
      <Wordmark />
      <h1 className="display mt-10 text-5xl font-black uppercase leading-none">Club area</h1>
      <p className="mt-4 max-w-[60ch] text-lg leading-relaxed text-fg-2">
        What a club would keep private: the staff report of every match of the matchday, with the knocks, how early the
        Risk Monitor warned about each one, and who was still at risk at full time. Any GitHub or Microsoft account opens it.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        {PROVIDERS.map((p) => (
          <a key={p.id} href={loginUrl(p.id)} className="btn btn-amber display px-6 py-3 text-lg font-black uppercase tracking-wide">{p.label}</a>
        ))}
      </div>
      <p className="mt-10 border-t border-line pt-4 text-base text-fg-2">
        The demo needs no sign-in. <a href="/" className="font-semibold text-amber underline underline-offset-4">Back to the match</a>
      </p>
    </section>
  )
}
