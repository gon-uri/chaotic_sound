<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-25 -->

# Duffing oscillator (forced)

> A spring with two resting places, shaken to a steady beat. It never loses the beat, yet its hops between the two places never repeat.

## In plain words

Picture a thin steel ruler hanging between two magnets. Left alone, it bends towards one magnet or the other and stays there, like a ball resting in either of two valleys. Now shake the frame from side to side at a steady tempo. Gentle shaking makes the ruler quiver near one magnet, in time. Shake harder and the pattern repeats only every 2 shakes, then every 4, then every 8. A little harder, and the ruler leaps to the other magnet at moments no one can predict.

Think of a drummer who never loses the tempo but chooses, chaotically, which of two drums to hit. Because the tempo comes from outside, this box is tuned exactly: the shaking *is* the note. The knob sets how hard the system is shaken, and so how wild the playing gets.

## Equations

$$
\begin{aligned}
\dot{x} &= y\\
\dot{y} &= -\delta\,y - \beta\,x - \alpha\,x^{3} + \gamma\cos z\\
\dot{z} &= \omega
\end{aligned}
$$

- $x$ is the displacement and $y$ the velocity. $z = \omega t$ is the drive phase, which makes the forced equation autonomous.
- $\delta = 0.1$ is the damping.
- $\beta = -1$ is the linear stiffness. Because it is negative, $x = 0$ is a hilltop.
- $\alpha = 1$ is the cubic stiffness, which pulls large swings back.
- $\gamma$ is the drive amplitude, the knob (default 0.35).
- $\omega = 1.4$ is the drive's angular frequency; the drive period is $2\pi/\omega \approx 4.488$.

So $\ddot x + 0.1\,\dot x - x + x^3 = \gamma\cos(1.4\,t)$: a ball in the potential $V(x) = -x^2/2 + x^4/4$, with valleys at $x = \pm 1$ and a hill of height $1/4$ between them. Small swings in a valley have angular frequency $\sqrt{2}$, close to the drive's 1.4.

**dysts [20] compared with other forms.**

- **Lettering.** A common form is $\ddot x + \delta\dot x + \alpha x + \beta x^3 = \gamma\cos\omega t$, with $\alpha$ linear [21]; dysts swaps the two letters. Holmes wrote $-\beta x$ with $\beta > 0$ [9].
- **The original.** Duffing (1918) studied a single-well spring with cubic (stiffening or softening) and quadratic (lopsided) corrections [1, 5]. The double well was made famous in 1979 by Holmes [9] and by Moon and Holmes [10], and is sometimes called the Duffing–Holmes oscillator. dysts' description, "a monochromatically-forced rigid pendulum", fits Duffing's single well better than these values.

## The parameter you control: γ

γ is how hard the system is shaken. Holmes found simple motion for weak and for strong forcing, and complicated motion over a wide range in between [9]. Melnikov's method [11, 12] gives the forcing above which the paths into and out of the hilltop cross and tangle:

$$
\gamma_c = \frac{4\,\delta\,\cosh(\pi\omega/2)}{3\sqrt{2}\,\pi\,\omega} \approx 0.098.
$$

Beyond $\gamma_c$ a "horseshoe" of chaotic orbits brings chaotic transients and can make the boundary between the two wells' basins fractal [13, 14]. It does not guarantee a lasting chaotic attractor [14]; here one appears only at about $3.5\,\gamma_c$. The landmarks below come from our own quick simulations, not from the literature, and agree with the project's sweep:

| γ | What happens |
|---|---|
| < 0.31 | Periodic rocking in one well (left or right, as mirror images). |
| ≈ 0.31–0.3405 | Period doubling: the motion repeats every 2, 4 (≈ 0.337), 8 (≈ 0.3397), then 16 (≈ 0.3403) drive cycles. |
| ≈ 0.3405 | Chaos, still confined to one well. |
| ≈ 0.341 | The two one-well attractors merge into one symmetric attractor that hops between wells (probably an attractor-merging crisis). |
| ≈ 0.341–0.355 | A small chaotic island that holds the default. |
| ≈ 0.355–0.375 | Period-5 window: two hops every five drive cycles. |
| ≈ 0.375–0.565 | Main chaotic band, with hops rising from about 0.45 to 0.8 per cycle. Hair-thin windows lie near 0.500 (period 3), 0.511 (period 5), 0.514 (period 7) and 0.517 (period 13). At 0.500 and 0.511 the orbit is reached only after a chaotic transient that can last thousands of cycles. |
| ≳ 0.57 | Period-3 subharmonic, while the large one-cycle swing (below) captures more and more starting states. |

The chaotic attractor is not alone. From γ ≈ 0.325 upward, across the whole knob range, it coexists with a large period-1 swing over both wells, which crosses the hill twice per drive cycle. In our checks a few percent of random starting states end on this swing near the default, rising to about a fifth or a quarter at the top of the range.

## Properties

- **Attractor:** a strange attractor. Strobed once per drive cycle (a Poincaré section), it is a folded, layered curve.
- **Lyapunov exponents:**
  - A long run gives $\lambda_1 \approx 0.13$ at the default. Shorter runs of a few hundred cycles, like the project's sweep (which gave 0.149), scatter between about 0.11 and 0.15. dysts lists 0.140.
  - $\lambda_2 = 0$ along the drive. The exponents sum to $-\delta$, so $\lambda_3 \approx -0.23$.
  - Per drive cycle $\lambda_1 P \approx 0.58$: nearby states separate by a factor $e$ in about 1.7 cycles.
- **Dimension:** Kaplan–Yorke $\approx 2.56$ from these exponents, the same value dysts lists. dysts also gives a correlation dimension of 2.02.
- **Dissipation:** the divergence is a constant $-\delta$. Each drive cycle shrinks Poincaré-section areas by $e^{-2\pi\delta/\omega} \approx 0.64$ [14]. That is far gentler than Lorenz, so transients are long and attractors often coexist.
- **Symmetry:** $(x, y, z) \mapsto (-x, -y, z + \pi)$. Cross-well chaos is symmetric, and one-well motions come in mirror pairs.
- **Phase coherence:**
  - The drive is a perfect clock, so the spectrum has a sharp line at the drive frequency over a broad chaotic floor.
  - $y$ keeps a quarter to a third of its power within ±3% of that line (about 0.24 at the default). $x$ keeps about 0.1, because well hopping feeds low frequencies.
  - Brunsden and Holmes predicted the shape of such spectra by treating the signal as a random train of near-homoclinic pulses, and compared the result with Duffing simulations [15].
- **Boundedness:** $|x| \lesssim 2$ across the range in our runs. $z$ grows forever, so the app wraps it modulo $2\pi$.

## History

**Duffing.** Georg Duffing (1861–1944) was born in Waldshut and trained as an engineer in Karlsruhe. After a spell at Westinghouse in the United States, he settled in Berlin in 1913 as an independent inventor and vibration researcher [3–5]. Machine vibrations motivated his 1918 booklet *Erzwungene Schwingungen bei veränderlicher Eigenfrequenz und ihre technische Bedeutung* ("Forced oscillations with variable natural frequency and their technical significance"; Vieweg, 134 pages) [1, 2]. The title states the key point: a nonlinear spring's natural frequency changes with amplitude. He checked approximate solutions against a pendulum apparatus [5].

**Kyoto, 1961.** On 27 November 1961, Yoshisuke Ueda, a graduate student in Chihiro Hayashi's laboratory at Kyoto University, was simulating a forced self-oscillator with a Duffing-type cubic spring. He was using a vacuum-tube analog computer built by his senior colleague M. Abe. The equation was $\ddot x - \mu(1-\gamma x^2)\dot x + x^3 = B\cos\nu t$, and its strobed points scattered over what he called a "broken egg" [16]. By 1963 he had seen the same behaviour in the Duffing equation itself [8].

The results fitted no accepted kind of oscillation and became a point of disagreement with Hayashi. Ueda's 1965 thesis sidestepped them, and his first chaotic examples appeared in Japanese in 1970 and 1973 [8]. In English, his 1979 paper [6] studied $\ddot x + k\dot x + x^3 = B\cos t$. With $k = 0.05$ and $B = 7.5$ it gives Ueda's attractor, nicknamed the "Japanese attractor". His 1980 paper [7] described the "explosion" of strange attractors, now called an interior crisis. H. B. Stewart notes that Yorke and colleagues, who coined that name, overlooked Ueda's priority [8].

**Holmes and the buckled beam, 1979.** Philip Holmes used Melnikov's 1963 method [11] to prove that the double-well equation has complicated motions, and mapped its attractor with analog and digital simulations [9]. That year Francis Moon and Holmes built a physical version [10]: a steel cantilever beam, buckled towards one of two magnets and shaken sinusoidally, which hopped chaotically between them. It became a teaching classic, rebuilt in 2013 as an undergraduate thesis project [14].

**Heard before it was understood.** In 1927 van der Pol and van der Mark listened to a driven neon-tube circuit through telephone receivers. Besides subharmonics, they reported that "an irregular noise is heard" before frequency jumps [17], a noise later read as chaos [18]. It was a different oscillator, but forced oscillators were literally heard being chaotic. Amplitude-dependent frequency, Duffing's theme, is musical too. Fletcher showed that a similar nonlinear shift in a shallow curved shell, whose pitch first falls and then rises as the vibration grows, explains the pitch glide of certain Chinese opera gongs [19]. Fletcher modelled a shell, not Duffing's spring; the comparison is ours.

## In chaotic_sound

All numbers are in the system's own time units.

- **Range:** the knob covers γ = 0.342–0.567. The default, 0.35, sits at 0.035 on the knob.
- **Tuning:** the tuning period is the drive period, $P = 2\pi/\omega \approx 4.488$, which is exact and identical at every γ (0% change across the range). With time rescaled by $k = P f_0$, the drive runs at exactly the note $f_0$; the measured tuning error is under one cent.
- **Heard variable:** $y$, which is locked to the drive and peaks at $f_0$. $x$ hops between wells, and subharmonics dominate its spectrum.
- **Chaos:** 85% of the 33 points of the project's range sweep are chaotic (the denser 130-point table in the current catalog gives 89%). $\lambda P$ mostly runs from about 0.5 to 1 per drive cycle, higher in the upper part of the range.
- **Main periodic window:** γ ≈ 0.355–0.375, about 0.055–0.145 on the knob, just above the default. (The coarse sweep puts its edges at 0.357 and 0.374.) The sound becomes the period-5 orbit, which repeats every five drive cycles. Its true fundamental is therefore $f_0/5$, two octaves and a major third below the note.
- **Tiny windows:** the sweep flags single grid points at γ ≈ 0.511 and 0.517 (knob ≈ 0.75 and 0.78), part of a cluster of hair-thin windows around 0.50–0.52 (see the table). Some take thousands of drive cycles to settle, which is several seconds at a mid-range note, so the box may sound chaotic there for a while.
- **A hidden steady tone:** the large one-cycle swing coexists with the chaos across the whole range (see above). A box that lands on it plays a steady, periodic tone at $f_0$ and stays there. Our simulations from the app's initial state did not land on it, but this is untested in the app, for example while the knob turns.
- **Range ends:** below γ ≈ 0.34 the motion is periodic inside one well. From γ ≈ 0.57 the period-3 subharmonic takes over ($f_0/3$, an octave and a fifth down), and the large one-cycle swing captures more starting states.
- **dysts' period:** dysts lists 7.45, which is not the drive period.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses (to be tested):

- $y$ should sound clearly pitched, with a breathy, crackling halo: a sharp line at the note over a broad chaotic floor. It is likely less pure than Rössler but steadier in pitch than the autonomous boxes.
- Sweeping γ should change roughness, not pitch. Crossing the 0.355–0.375 window should snap to a clean, buzzy tone whose pitch may drop towards $f_0/5$. If the state falls onto the large one-cycle swing, the box should instead hold a steady tone at the note with no chaotic halo.
- $x$ will likely sound like an irregular, lurching sub-bass with only a faint pitch.

## References

1. Duffing, G. (1918). *Erzwungene Schwingungen bei veränderlicher Eigenfrequenz und ihre technische Bedeutung*. Sammlung Vieweg, Heft 41/42. Braunschweig: F. Vieweg & Sohn. VI + 134 pp.
2. Hamel (1921). Review of Duffing (1918). *ZAMM – Zeitschrift für Angewandte Mathematik und Mechanik*, 1(1), 72–73. https://doi.org/10.1002/zamm.19210010109 (this is the DOI that dysts lists for the system)
3. Kovacic, I., & Brennan, M. J. (2011). Background: On Georg Duffing and the Duffing equation. In I. Kovacic & M. J. Brennan (Eds.), *The Duffing Equation: Nonlinear Oscillators and their Behaviour* (pp. 1–23). Wiley. https://doi.org/10.1002/9780470977859.ch1
4. Rimrott, F. P. J. (1994). Georg Duffing (1861–1944). *Technische Mechanik*, 14(1), 77–82. https://journals.ub.ovgu.de/index.php/techmech/article/view/1285
5. Nolte, D. D. (2019, updated 2023). Georg Duffing and his equation. *Galileo Unbound* (blog). https://galileo-unbound.blog/2019/03/20/georg-duffing-and-his-equation/
6. Ueda, Y. (1979). Randomly transitional phenomena in the system governed by Duffing's equation. *Journal of Statistical Physics*, 20(2), 181–196. https://doi.org/10.1007/BF01011512
7. Ueda, Y. (1980). Explosion of strange attractors exhibited by Duffing's equation. *Annals of the New York Academy of Sciences*, 357, 422–434. https://doi.org/10.1111/j.1749-6632.1980.tb29708.x
8. Ueda, Y. (1992). *The Road to Chaos*. Santa Cruz: Aerial Press. Includes a preface and chronology by R. H. Abraham and technical comments by H. B. Stewart. Front matter: https://repository.kulib.kyoto-u.ac.jp/dspace/handle/2433/71101
9. Holmes, P. (1979). A nonlinear oscillator with a strange attractor. *Philosophical Transactions of the Royal Society of London A*, 292(1394), 419–448. https://doi.org/10.1098/rsta.1979.0068
10. Moon, F. C., & Holmes, P. J. (1979). A magnetoelastic strange attractor. *Journal of Sound and Vibration*, 65(2), 275–296. https://doi.org/10.1016/0022-460X(79)90520-0
11. Mel'nikov, V. K. (1963). On the stability of a center for time-periodic perturbations. *Trudy Moskovskogo Matematicheskogo Obshchestva*, 12, 3–52. English translation: *Transactions of the Moscow Mathematical Society*, 12, 1–56. https://www.mathnet.ru/eng/mmo137
12. Guckenheimer, J., & Holmes, P. (1983). *Nonlinear Oscillations, Dynamical Systems, and Bifurcations of Vector Fields* (§4.5). Springer. https://doi.org/10.1007/978-1-4612-1140-2
13. Moon, F. C., & Li, G.-X. (1985). Fractal basin boundaries and homoclinic orbits for periodic motion in a two-well potential. *Physical Review Letters*, 55(14), 1439–1442. https://doi.org/10.1103/PhysRevLett.55.1439
14. Tam, J. I., & Holmes, P. (2014). Revisiting a magneto-elastic strange attractor. *Journal of Sound and Vibration*, 333(6), 1767–1780. https://doi.org/10.1016/j.jsv.2013.11.022
15. Brunsden, V., & Holmes, P. (1987). Power spectra of strange attractors near homoclinic orbits. *Physical Review Letters*, 58(17), 1699–1702. https://doi.org/10.1103/PhysRevLett.58.1699
16. Ueda, Y. (2010). At the very instant when the author came across an inexperienced behavior. *Proceedings of the 3rd International Conference on Nonlinear Dynamics (ND-KhPI2010)*, Kharkov, 213–218. https://www.kpi.kharkov.ua/archive/Conferences/nonlinear%20dynamics/2010/AT%20THE%20VERY%20INSTANT%20WHEN%20THE%20AUTHOR%20CAME%20ACROSS%20AN%20INEXPERIENCED%20BEHAVIOR.pdf
17. van der Pol, B., & van der Mark, J. (1927). Frequency demultiplication. *Nature*, 120, 363–364. https://doi.org/10.1038/120363a0
18. Kennedy, M. P., & Chua, L. O. (1986). Van der Pol and chaos. *IEEE Transactions on Circuits and Systems*, 33(10), 974–980. https://doi.org/10.1109/TCS.1986.1085855
19. Fletcher, N. H. (1985). Nonlinear frequency shifts in quasispherical-cap shells: Pitch glide in Chinese gongs. *Journal of the Acoustical Society of America*, 78(6), 2069–2073. https://doi.org/10.1121/1.392664
20. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code: https://github.com/GilpinLab/dysts
21. Wikipedia contributors. Duffing equation. *Wikipedia*. https://en.wikipedia.org/wiki/Duffing_equation (cited only for the common lettering of the coefficients)
