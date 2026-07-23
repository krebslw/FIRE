from scipy.stats import t, norm

__all__ = [
    "HypothesisTest",
    "Ztest",
    "Ttest",
]


class HypothesisTest:
    """Conduct a statistical hypothesis test."""

    def __init__(
        self,
        std_est: float,
        critival_value: float,
        H0: float = 0,
        alpha: float = 0.05,
    ):
        self.H0 = H0
        self.alpha = alpha
        self.std_est = std_est
        self.critical_value = critival_value

    @property
    def score(self) -> float:
        """Return the test's score."""
        return abs(self.H0 / self.std_est)

    @property
    def H0accepted(self) -> bool:
        """
        Evaluate the test's result.

        If H0 is accepted, it means that a significant difference between the tested
        parameter and the reference value could not be detected.

        Conversely, if H0 is rejected, there is a probability of `alpha` or higher, that
        the test-parameter is different from the reference.
        """
        return bool(self.score < self.critical_value)


class Ztest(HypothesisTest):
    """Conduct two-sided Z-test"""

    def __init__(self, std_est: float, H0: float = 0, alpha: float = 0.05):

        critical_value = norm.ppf(1 - alpha / 2)
        super().__init__(std_est, critical_value, H0, alpha)


class Ttest(HypothesisTest):
    """Conduct two-sided T-test"""

    def __init__(
        self,
        std_est: float,
        dof: int,
        H0: float = 0,
        alpha: float = 0.05,
    ):
        self.dof = dof
        critical_value = t.ppf(1 - alpha / 2, dof)
        super().__init__(std_est, critical_value, H0, alpha)
