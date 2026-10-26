<!-- Draft written by an AI agent; facts need human review before publishing. Last updated: 2026-10-26 -->

# Rössler system

> A deliberately minimal recipe for chaos: a slow outward spiral, a sudden lift, a drop back to the centre, and a tone that almost repeats but never quite does.

## In plain words

Picture a marble circling in a dish that gently pushes it outward, so each lap is a little wider than the last. When a lap gets wide enough, a third ingredient flips the marble up and over and drops it back near the centre, and the slow spiral starts again. The landing spot is never quite the same, so the next run of laps is never quite the same either. The spiral stretches neighbouring paths apart, and the flip folds the stretched band back over itself, the way a taffy-pulling machine works candy.

For a musician, the key point is that every lap takes almost the same time. One lap is one cycle of the waveform, and by our measurements this is the most clearly pitched system in the app. What wanders is the size of each lap. So we expect the chaos to sound less like noise and more like an irregular breathing on top of a clear note (still to be confirmed by listening).

## Equations

$$
\begin{aligned}
\dot{x} &= -y - z\\
\dot{y} &= x + a\,y\\
\dot{z} &= b + z\,(x - c)
\end{aligned}
$$

- $x$ and $y$ are the rotating pair. With $z = 0$ they form an oscillator that turns about once every $2\pi$ time units while slowly spiralling outward.
- $z$ acts as a switch. It stays near zero for most of each lap and fires a short, tall spike when $x$ climbs above $c$. The spike throws the orbit back towards the centre, through the $-z$ in $\dot x$.
- $a = 0.2$ sets how fast the spiral unwinds.
- $b = 0.2$ is a small constant feed into $z$, which keeps $z$ positive.
- $c = 5.7$ is the firing threshold. This is the parameter the knob controls; the app's default is 6.5625 (see "In chaotic_sound").

There is only one nonlinear term, $zx$; Lorenz's system has two.

**dysts compared with the original.** dysts uses Rössler's form with $a = b = 0.2$ and $c = 5.7$, citing his 1976 letter [1, 19]. These are the values Rössler himself gives when he recalls finding the system [3, 5]. Later work often uses other values (the Scholarpedia article, for instance, uses $a = 0.432$, $b = 2$, $c = 4$ [5]). Although the model was inspired by chemistry, $x$ and $y$ go negative, so they are not concentrations: it is an abstract prototype.

## The parameter you control: $c$

$c$ sets how wide the spiral may grow before the switch fires, so raising it makes the laps larger and the $z$ spikes taller. With $a = b = 0.2$, increasing $c$ gives the textbook period-doubling route to chaos [18]:

| $c$ | What happens ($a = b = 0.2$) |
|---|---|
| below ≈ 2.83 | One simple loop (period 1), e.g. $c = 2.5$. |
| ≈ 2.8324 | First period doubling, proved with computer assistance [15]. Two alternating laps (e.g. $c = 3.5$). |
| ≈ 3.8374 | Second period doubling (period 4, e.g. $c = 4$), also proved in [15]. |
| ≈ 4.1 | Period 8, then ever faster doublings. |
| ≈ 4.2 | The cascade accumulates. Chaos first appears in 4 and then 2 separate bands, which merge into a single band at $c \approx 4.5$. |
| ≈ 5.19–5.5 | Period-3 window: period 3, then doublings to 6 and 12, then chaos again. |
| 5.7 | Rössler's classical value. |
| ≈ 8.1 and above | Some small laps stop circling the centre: the attractor becomes partly "funnel"-like. |

The first two doubling values are from the literature [15]. The others come from our own simulations, not from a published table. The pattern of doublings, band mergings and windows is the one familiar from one-hump maps such as the logistic map. Plot each maximum of $x$ against the next and the points fall close to a single humped curve [5, 20].

## Properties

- **Attractor:** a single band that is stretched, folded and laid back on itself, not the two wings of Lorenz [5]. It is extremely thin. Its Kaplan–Yorke dimension is about 2.01 (2.013 from the exponents below; dysts gives 2.015), so it is nearly a surface.
- **Equilibria:** there are two, at $(a z_\pm,\ -z_\pm,\ z_\pm)$ with $z_\pm = \big(c \pm \sqrt{c^2 - 4ab}\big)/(2a)$.
  - The inner one, at about $(0.007, -0.035, 0.035)$, is the centre of the spiral. It is a saddle-focus with eigenvalues of about $0.097 \pm 0.995i$ and $-5.69$.
  - The outer one, at about $(5.69, -28.5, 28.5)$, lies far outside the attractor.
- **Symmetry:** none, so there is no mirror lobe.
- **Dissipation:** the divergence is $a + x - c$, which varies along the orbit. Its average is about $-5.32$ per time unit, the sum of the Lyapunov exponents.
- **Lyapunov exponents:**
  - This project measures $\lambda \approx 0.071$ at $c = 5.7$ (four runs of 60,000 time units each).
  - Kuptsov and Kuznetsov give $(0.072,\ \approx 0,\ -5.394)$ [16]. Our own spectrum computation agrees.
  - dysts lists $\lambda_{\max} \approx 0.15$, about twice the other estimates, but its own spectrum estimate starts at 0.076 [19].
  - Per lap, $\lambda P \approx 0.4$, so nearby paths separate by about ×1.5 per lap. Lorenz is about 0.7 per loop (0.6–0.7 across its range).
- **Phase coherence:**
  - At the classical value $c = 5.7$, and also at the app's default $c = 6.5625$, the $x$–$y$ motion always turns the same way around the inner equilibrium. The angle around that centre is therefore a good phase and grows almost uniformly, which gives a sharp spectral peak on a broad base.
  - The Santa Cruz group studied this system's spectra in 1980 [9] and named the property "phase coherence" in a companion paper [10]. It made Rössler the standard model for phase synchronization: two coupled Rössler oscillators can lock their phases while their amplitudes stay chaotic [11, 12].
  - If small loops start to miss the centre, the attractor becomes a non-coherent "funnel", in which the phase is ill-defined and the peak broadens [12, 13]. That literature usually reaches it by raising $a$ (exact parameter values unverified). In our simulations at $a = b = 0.2$, a few percent of laps already miss the centre from $c \approx 8.1$.
- **Boundedness and rigour:**
  - $z$ never goes negative, since $\dot z = b > 0$ at $z = 0$.
  - The attractor is bounded, but some starting points and parameter values send orbits to infinity [17].
  - A computer-assisted proof shows that the classical system contains chaotic symbolic dynamics [14].

## History

**A medical graduate with an analog computer.** Otto E. Rössler, born in Berlin in 1940 (unverified), studied medicine but never practised it [3]. He then worked at the Max Planck Institute for Behavioural Physiology in Seewiesen, where he befriended the ethologist Konrad Lorenz (no relation of Edward). In 1970 he joined Friedrich-Franz Seelig's group in Tübingen. There an analog computer, a Dornier DO 240, let him wire up small reaction schemes like electronic circuits [3].

**Winfree's challenge.** At a chronobiology meeting in Vienna in 1975, Rössler described to the biologist Arthur Winfree a three-variable limit cycle shaped like a knot. Winfree said it sounded like chaos. Fresh from a meeting on chaos in Aspen, Winfree mailed him a folder of papers a few weeks later, including Lorenz's 1963 paper, and asked for a chemical version of the Lorenz attractor [3, 4].

**The 1976 papers.** Rössler did not find a chemical Lorenz attractor, so he settled for something simpler [3, 5]. In 1976 he published a paper on chaos in simple reaction models [2] and a two-page letter in *Physics Letters A* giving the equation now named after him [1]. He recalls starting from an image of a rope wrapped around his nose that falls off and loops back [3, 5]. His accounts of the next step differ: in 2021 he describes turning the analog computer's knobs and simplifying [3], in 2006 the simplified equations taking shape on a slow HP 9820A desktop computer [5]. To explain the stretching and folding he used a taffy-pulling machine; Ulrich Parlitz remembers his taffy-puller slides at a seminar in Göttingen [3]. Igra traces the inspiration to Rössler's 1983 paper [6, 20], which we have not checked. Soon after, Lars Folke Olsen and Hans Degn found chaos in a real enzyme reaction. Olsen had visited Rössler in Tübingen, and when he described his irregular oscillations, Rössler told him to read Lorenz [3, 8].

**The sound of chaos.** With Reimara Waible, Rössler made a film on the analog computer with the "sound of chaos", a title that plays on Simon and Garfunkel's "The Sound of Silence". He recalls that the sound was "familiar to the ear", and he took that as a sign that chaos is close to everyday life [3].

**Name and legacy.** Rössler credits Norman Packard, Rob Shaw, Jim Crutchfield and Doyne Farmer of Santa Cruz with coining the name "Rössler attractor" [3]. In 1979 he used a four-variable system to introduce hyperchaos, chaos with two positive Lyapunov exponents [7]. The 1976 system went on to become a textbook example of period doubling [18], the workhorse of phase synchronization [11] and a test bed for computer-assisted proofs [14, 15].

## In chaotic_sound

Numbers are in the system's own time units.

- **The knob** sweeps $c$ from 4.2375 to 8.8151. The default, 6.5625, sits at 0.51 on the knob. Under the project's range rules the default is the chaotic value nearest the middle of the range, and its nearest neighbours on both sides must be chaotic too, so it never sits at the edge of a periodic window. Rössler's classical 5.7, the value dysts uses, now sits at 0.32 on the knob and is kept only as a reference.
- **How chaotic it is.** The project calls a point chaotic when $\lambda P > 0.05$, where $P = 5.8556$ is the lap time measured at $c = 5.7$. By that test 78% of the 130 table points in the range are chaotic, including both ends. At the default $\lambda \approx 0.085$, so nearby paths separate by about ×1.65 per lap ($\lambda P \approx 0.5$), a little faster than at 5.7. The chaos is gentlest at the bottom ($\lambda P \approx 0.1$ at 4.24, about ×1.1 per lap) and strongest near the top (about 0.5–0.6).
- **Tuning.** The app tunes from $x$, the variable with the sharpest spectral peak. Its prominence (the share of its power in that peak) is 0.79 at the default and never drops below 0.48 across the range, well above the project's minimum of 0.15. The period is measured as the *peak centroid*: the power-weighted average frequency of the spectral peak (within ±10% of it), which is steadier than picking the single strongest frequency. At the default $P = 5.8864$ time units; dysts lists 5.9086, 0.4% longer. To play $f_0$, the engine advances $k = P \cdot f_0$ time units per second, about 2,590 for A4 = 440 Hz.
- **An almost fixed period.** Across the whole range $P$ moves only between 5.743 and 5.940: 3.4%, about 58 cents, just over half a semitone. It never changes by more than 1.9% between neighbouring table points, so the pitch-lock table is smooth. The shortest periods occur inside the period-5 window (see below); over the chaotic points alone the spread is 5.787–5.940 (45 cents). A likely reason for this steadiness is that the turning rate comes from the $x$–$y$ oscillator, which does not contain $c$. With pitch lock on, the engine follows the table and the note stays put. With it off, the note drifts at most from about 16 cents flat (near the top) to 43 cents sharp (in the period-5 window). Either way, we expect the knob to change mainly the colour and roughness of the sound, not its pitch (to be confirmed by listening).
- **Periodic windows.** Eleven spots inside the range are not chaotic ($\lambda P < 0.05$ on the 130-point table, whose points are about 0.036 apart). Three are stretches wide enough to find easily (lap counts from our own simulations):
  - $c \approx 5.20$–5.49 (knob 0.21–0.27): the period-3 window from the table above. The motion repeats every 3 laps, doubling to 6 and then 12 laps towards the top of the window.
  - $c \approx 6.67$–6.78 (knob 0.53–0.55): a period-4 window (8 laps at its top end). It lies just above the default, so pushing $c$ up from the default reaches it quickly.
  - $c \approx 7.89$–8.10 (knob 0.80–0.84): a period-5 window (10 laps at its top end).

  The other eight are single table points, at $c \approx$ 4.38, 4.70, 5.67, 5.99, 7.06, 7.35, 7.53 and 7.74, so each is narrower than about 0.07 in $c$ (under 1.6% of the knob). At most of them our simulations find a cycle that repeats exactly after 5 to 9 laps (for example 5 laps at 4.70 and 5.99, 7 at 7.06 and 7.53). The one at 5.67 lies just below the classical value 5.7.

  **What a window does to the sound.** An $n$-lap cycle repeats exactly, so we expect the irregular breathing to stop and the tone to turn steady. The cycle also adds spectral lines at multiples of $f_0/n$. In our spectra of $x$ the strongest new line sits just below the note: $2f_0/3$, a fifth below, in the period-3 window, where it is weak (under a tenth of the note's power); $3f_0/4$, a fourth below, in the period-4 window (about a quarter); and $4f_0/5$, a major third below, in the period-5 window (about a third). Pitch lock keeps the note itself on $f_0$ through every window. We expect the single-point windows to be audible only when the knob rests on them.
- **Levels.** $x$ and $y$ play at the app's normal level. $z$ is a train of tall spikes: its robust peak (the 99.9th percentile) is about 8 times its standard deviation at the default, from about 6 at the bottom to 11 at the top. The engine limits each box's gain by that peak so that it does not clip, so $z$ plays about 8 dB quieter than $x$ at the default (about 5 dB at the bottom, 11 dB at the top).
- **Why the range ends where it does.**
  - *Bottom, 4.2375: where chaos begins.* The lab's sweep starts at $c = 3$ and found nothing unsafe below the range. From 3 up to about 4.2 the system runs through the period-doubling cascade (one loop, then cycles of 2, 4, 8 and 16 laps), which is bounded, steady and clearly pitched, but periodic. The project wants both ends of the knob to be chaotic, so the range starts at the first chaotic value of the sweep, 4.2375, just past the point where the cascade accumulates. This end is set by the chaos rule alone, not by a safety problem.
  - *Top, 8.8151: where the pitch would jump.* The coarse sweep (values 0.0375 apart) saw the measured period jump by 24% at $c \approx 8.96$. The finer table pass (130 points, about 0.036 apart) found a 19% jump already at 8.852 and moved the end to the table point just below it. A jump of that size, about 3 semitones, would make pitch lock glitch. Our own check suggests why it happens: at $c \approx 8.85$ the motion locks into a five-lap cycle in which one lap in five is a small loop that skips the centre (the funnel behaviour described under Properties). That cycle has two almost equally strong spectral lines, one at the lap rate and one whose period is about 19% longer, and the measurement lands on the longer one. Even before that point, from just above the period-5 window ($c \approx 8.14$), about 4–10% of laps miss the centre. The top of the range is therefore partly funnel-like, and there the prominence of $x$ falls to about 0.5.

## Sound notes

To be filled in after listening tests (Phase 1).

Hypotheses (to be tested):

- $x$ should be the most clearly pitched box: a near-pure tone whose loudness breathes irregularly, rather than one that hisses. The reasons are its very sharp peak (prominence ≈ 0.79 at the default, above 0.9 near the bottom of the range) and its slow chaos ($\lambda P \approx 0.5$ at the default).
- $z$, if exposed, should sound buzzy and bright at the same pitch, since it is a train of narrow spikes. It should also sound softer than $x$ (about 8 dB at the default), because its tall spikes set its level limit.
- Raising $c$ should roughen the tone with little pitch change, from almost steady at the bottom ($\lambda P \approx 0.1$) to roughest near the top. In the three wide windows (5.20–5.49, 6.67–6.78 and 7.89–8.10) the tone should turn steady, with an extra line a fifth, a fourth or a major third below the note respectively; the last two may be clearly audible. Above $c \approx 8.14$, where some laps skip the centre, the pitch may sound a little less clean.

## References

1. Rössler, O. E. (1976). An equation for continuous chaos. *Physics Letters A*, 57(5), 397–398. https://doi.org/10.1016/0375-9601(76)90101-8
2. Rössler, O. E. (1976). Chaotic behavior in simple reaction systems. *Zeitschrift für Naturforschung A*, 31(3–4), 259–264. https://doi.org/10.1515/zna-1976-3-408
3. Letellier, C., Abraham, R., Shepelyansky, D. L., Rössler, O. E., et al. (2021). Some elements for a history of the dynamical systems theory. *Chaos*, 31(5), 053110. Section IV, "My Dance with Chaos", is by O. E. Rössler; Section XII is by U. Parlitz. https://doi.org/10.1063/5.0047851
4. Letellier, C., & Messager, V. (2010). Influences on Otto E. Rössler's earliest paper on chaos. *International Journal of Bifurcation and Chaos*, 20(11), 3585–3616. https://doi.org/10.1142/S0218127410027854
5. Letellier, C., & Rössler, O. E. (2006). Rössler attractor. *Scholarpedia*, 1(10), 1721. Includes Rössler's own reminiscences. https://doi.org/10.4249/scholarpedia.1721
6. Rössler, O. E. (1983). The chaotic hierarchy. *Zeitschrift für Naturforschung A*, 38(7), 788–801. https://doi.org/10.1515/zna-1983-0714 (Cited by Igra [20] for the taffy-puller inspiration; not checked in the original.)
7. Rössler, O. E. (1979). An equation for hyperchaos. *Physics Letters A*, 71(2–3), 155–157. https://doi.org/10.1016/0375-9601(79)90150-6
8. Olsen, L. F., & Degn, H. (1977). Chaos in an enzyme reaction. *Nature*, 267, 177–178. https://doi.org/10.1038/267177a0
9. Crutchfield, J. P., Farmer, J. D., Packard, N. H., Shaw, R. S., Jones, G., & Donnelly, R. J. (1980). Power spectral analysis of a dynamical system. *Physics Letters A*, 76(1), 1–4. https://doi.org/10.1016/0375-9601(80)90130-9
10. Farmer, J. D., Crutchfield, J. P., Froehling, H., Packard, N. H., & Shaw, R. S. (1980). Power spectra and mixing properties of strange attractors. *Annals of the New York Academy of Sciences*, 357, 453–471. https://doi.org/10.1111/j.1749-6632.1980.tb29710.x
11. Rosenblum, M. G., Pikovsky, A. S., & Kurths, J. (1996). Phase synchronization of chaotic oscillators. *Physical Review Letters*, 76(11), 1804–1807. https://doi.org/10.1103/PhysRevLett.76.1804
12. Pikovsky, A., Rosenblum, M., & Kurths, J. (2001). *Synchronization: A Universal Concept in Nonlinear Sciences*. Cambridge University Press. https://doi.org/10.1017/CBO9780511755743
13. Osipov, G. V., Hu, B., Zhou, C., Ivanchenko, M. V., & Kurths, J. (2003). Three types of transitions to phase synchronization in coupled chaotic oscillators. *Physical Review Letters*, 91(2), 024101. https://doi.org/10.1103/PhysRevLett.91.024101
14. Zgliczyński, P. (1997). Computer assisted proof of chaos in the Rössler equations and in the Hénon map. *Nonlinearity*, 10(1), 243–252. https://doi.org/10.1088/0951-7715/10/1/016
15. Wilczak, D., & Zgliczyński, P. (2009). Period doubling in the Rössler system—a computer assisted proof. *Foundations of Computational Mathematics*, 9(5), 611–649. https://doi.org/10.1007/s10208-009-9040-x (preprint: arXiv:0712.1123)
16. Kuptsov, P. V., & Kuznetsov, S. P. (2018). Lyapunov analysis of strange pseudohyperbolic attractors: angles between tangent subspaces, local volume expansion and contraction. *Regular and Chaotic Dynamics*, 23(7–8), 908–932. https://doi.org/10.1134/S1560354718070079
17. Barrio, R., Blesa, F., & Serrano, S. (2014). Unbounded dynamics in dissipative flows: Rössler model. *Chaos*, 24(2), 024407. https://doi.org/10.1063/1.4871712
18. Strogatz, S. H. (2024). *Nonlinear Dynamics and Chaos* (3rd ed.). CRC Press. https://doi.org/10.1201/9780429398490
19. Gilpin, W. (2021). Chaos as an interpretable benchmark for forecasting and data-driven modelling. *NeurIPS Datasets and Benchmarks Track*. arXiv:2110.05266. Code and metadata: https://github.com/GilpinLab/dysts
20. Igra, E. (2023/2024). One dimensional dynamics and the Rössler attractor. arXiv:2312.13840. https://arxiv.org/abs/2312.13840
