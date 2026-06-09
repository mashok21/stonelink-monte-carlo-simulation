from rest_framework import serializers


class SimulationRequestSerializer(serializers.Serializer):
    PORTFOLIO_CHOICES = ("Min Risk", "Balanced", "Growth", "High Return")
    ENVIRONMENT_CHOICES = ("STANDARD_CRUISE", "MARKET_STRESS")
    TARGET_MODE_CHOICES = ("default", "custom")
    SUCCESS_FRAMEWORK_CHOICES = (
        "institutional_sustainability",
        "continuous_solvency",
        "terminal_assets",
        "terminal_asset_preservation",
        "total_value",
        "real_return_target",
    )

    initial_portfolio_value = serializers.FloatField(min_value=1.0, max_value=1_000_000_000_000.0, default=100000.0)
    years = serializers.IntegerField(min_value=1, max_value=100, default=30)
    contribution_rate = serializers.FloatField(min_value=0.0, max_value=100.0, default=3.0)
    distribution_rate = serializers.FloatField(min_value=0.0, max_value=100.0, default=4.0)
    annual_contribution = serializers.FloatField(min_value=0.0, max_value=100.0, required=False)
    annual_withdrawal = serializers.FloatField(min_value=0.0, max_value=100.0, required=False)
    withdrawal_start_year = serializers.IntegerField(min_value=0, max_value=100, default=15)
    inflation_rate = serializers.FloatField(min_value=-25.0, max_value=100.0, default=2.5)
    num_trials = serializers.IntegerField(min_value=10, max_value=10000, default=1000)
    min_reserve_threshold_ratio = serializers.FloatField(min_value=0.0, max_value=100.0, default=20.0)
    success_framework = serializers.ChoiceField(choices=SUCCESS_FRAMEWORK_CHOICES, default="institutional_sustainability")
    success_mode = serializers.ChoiceField(choices=("terminal_assets", "total_value"), required=False, allow_null=True)
    enable_hard_liquidation = serializers.BooleanField(default=False)
    portfolio_type = serializers.ChoiceField(choices=PORTFOLIO_CHOICES, default="Balanced")
    target_hurdle = serializers.FloatField(min_value=0.0, max_value=1_000_000_000_000.0, required=False, allow_null=True)
    target_mode = serializers.ChoiceField(choices=TARGET_MODE_CHOICES, default="default")
    environment_mode = serializers.ChoiceField(choices=ENVIRONMENT_CHOICES, default="STANDARD_CRUISE")
    use_fixed_seed = serializers.BooleanField(default=True)
    include_audit = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if "annual_contribution" in attrs:
            if "contribution_rate" in self.initial_data:
                raise serializers.ValidationError({
                    "annual_contribution": "Provide either 'contribution_rate' or 'annual_contribution', not both."
                })
            attrs["contribution_rate"] = attrs["annual_contribution"]
        if "annual_withdrawal" in attrs:
            if "distribution_rate" in self.initial_data:
                raise serializers.ValidationError({
                    "annual_withdrawal": "Provide either 'distribution_rate' or 'annual_withdrawal', not both."
                })
            attrs["distribution_rate"] = attrs["annual_withdrawal"]

        if attrs["withdrawal_start_year"] > attrs["years"]:
            raise serializers.ValidationError({
                "withdrawal_start_year": "Must be less than or equal to years."
            })

        if attrs["target_mode"] == "custom" and attrs.get("target_hurdle") is None:
            raise serializers.ValidationError({
                "target_hurdle": "Required when target_mode is custom."
            })

        if attrs.get("success_framework") == "terminal_asset_preservation":
            attrs["success_framework"] = "terminal_assets"
        elif attrs.get("success_framework") == "real_return_target":
            attrs["success_framework"] = "total_value"

        if "success_framework" in self.initial_data:
            attrs["success_mode"] = attrs.get("success_mode")
        else:
            attrs["success_mode"] = attrs.get("success_mode", "total_value")

        attrs["target_hurdle"] = attrs.get("target_hurdle")
        if attrs["target_hurdle"] is None:
            attrs["target_hurdle"] = attrs["initial_portfolio_value"]

        return attrs
