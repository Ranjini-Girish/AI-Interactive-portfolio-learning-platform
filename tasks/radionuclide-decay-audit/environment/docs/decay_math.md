# Decay Mathematics Reference

## Decay Constant

For an isotope with half-life t½ (in hours):

    λ = ln(2) / t½

Stable isotopes have `half_life_hours: null` and λ = 0.

## Activity

Activity (in Bq) is the rate of disintegrations:

    A(t) = λ × N(t)

where N(t) is the atom count at time t. Stable isotopes always have
activity zero regardless of atom count.

## Initial Conditions

Sample files specify initial activities A₀ in Bq. Convert to initial
atom counts:

    N(0) = A(0) / λ

Isotopes not listed in a sample's `initial_activities_bq` have N(0) = 0.

## Two-Isotope Chain (Parent → Daughter)

For parent P decaying to daughter D with branching ratio b:

    N_D(t) = N_D(0) × exp(-λ_D × t)
           + b × λ_P × N_P(0) / (λ_D − λ_P) × [exp(-λ_P × t) − exp(-λ_D × t)]

This formula is valid when λ_P ≠ λ_D.

## Near-Degenerate Case

When |λ_P − λ_D| / max(λ_P, λ_D) < `nearly_equal_lambda_rel_tol`
(from policy.json), the standard formula suffers catastrophic
cancellation. Use the limiting form instead:

    N_D(t) = N_D(0) × exp(-λ_D × t)
           + b × λ_P × N_P(0) × t × exp(-λ_P × t)

The policy threshold determines when to switch between the two forms.

## Branching Decay

When an isotope has multiple decay modes, each daughter receives atoms
at a rate proportional to its branching ratio. The branching ratios for
a given parent always sum to 1.0.

## Dose Rate

Dose rate from a collection of isotopes:

    D(t) = Σᵢ A_i(t) × c_i

where c_i is the `dose_coefficient_sv_per_bq_h` from isotopes.json.

## Secular Equilibrium

For a parent-daughter pair where λ_parent < λ_daughter (parent is
longer-lived), secular equilibrium occurs when:

    A_daughter ≈ b × A_parent

where b is the branching ratio. The `equilibrium_ratio_tolerance` in
policy.json defines how close the ratio must be.

## Minimum Activity Threshold

Activities below `min_activity_bq` (from policy.json) should be treated
as zero in the output.
