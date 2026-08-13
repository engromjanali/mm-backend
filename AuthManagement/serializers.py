from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


class AliasInputMixin:
    input_aliases = {}

    def to_internal_value(self, data):
        data = data.copy()
        for alias, field in self.input_aliases.items():
            if alias in data and field not in data:
                data[field] = data[alias]
        return super().to_internal_value(data)


class UserProfileSerializer(AliasInputMixin, serializers.ModelSerializer):
    input_aliases = {
        "Photo": "photo",
        "full-name": "full_name",
        "fullName": "full_name",
        "Email": "email",
        "Phone": "phone",
        "Password": "password",
        "Address": "address",
        "let": "lat",
        "latitude": "lat",
        "longitude": "long",
    }
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    lat = serializers.DecimalField(
        source="latitude", max_digits=10, decimal_places=7, required=False, allow_null=True
    )
    long = serializers.DecimalField(
        source="longitude", max_digits=10, decimal_places=7, required=False, allow_null=True
    )

    class Meta:
        model = User
        fields = ["id", "photo", "full_name", "email", "phone", "password", "address", "lat", "long"]
        read_only_fields = ["id"]

    def validate_password(self, value):
        user = self.instance
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate_email(self, value):
        value = User.objects.normalize_email(value).lower()
        users = User.objects.filter(email__iexact=value)
        if self.instance:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        value = value.strip()
        users = User.objects.filter(phone=value)
        if self.instance:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise serializers.ValidationError("A user with this phone already exists.")
        return value

    def validate_lat(self, value):
        if value is not None and not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_long(self, value):
        if value is not None and not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class SignUpSerializer(AliasInputMixin, serializers.ModelSerializer):
    input_aliases = {
        "full-name": "full_name",
        "fullName": "full_name",
        "Email": "email",
        "Phone": "phone",
        "Password": "password",
    }
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["full_name", "email", "phone", "password"]

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate_email(self, value):
        value = User.objects.normalize_email(value).lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_phone(self, value):
        value = value.strip()
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("A user with this phone already exists.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class SignInSerializer(AliasInputMixin, serializers.Serializer):
    input_aliases = {"Type": "type", "Password": "password"}
    type = serializers.ChoiceField(choices=["email", "phone"])
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        sign_in_type = attrs["type"]
        identifier = attrs.get(sign_in_type)
        if not identifier:
            raise serializers.ValidationError(
                {sign_in_type: f"This field is required when type is {sign_in_type}."}
            )

        lookup = {f"{sign_in_type}__iexact": identifier}
        user = User.objects.filter(**lookup).first()
        if not user or not user.check_password(attrs["password"]):
            raise serializers.ValidationError("Invalid sign-in credentials.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        attrs["user"] = user
        return attrs

    def to_internal_value(self, data):
        data = data.copy()
        sign_in_type = data.get("type", data.get("Type"))
        identifier = data.get("email/phone", data.get("identifier"))
        if sign_in_type in ("email", "phone") and identifier and sign_in_type not in data:
            data[sign_in_type] = identifier
        return super().to_internal_value(data)


class ForgotPasswordSerializer(AliasInputMixin, serializers.Serializer):
    input_aliases = {"Type": "type", "Email": "email", "Phone": "phone"}
    type = serializers.ChoiceField(choices=["email", "phone"])
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)

    def validate(self, attrs):
        identifier_field = attrs["type"]
        if not attrs.get(identifier_field):
            raise serializers.ValidationError(
                {identifier_field: f"This field is required when type is {identifier_field}."}
            )
        return attrs


class RefreshTokenSerializer(AliasInputMixin, serializers.Serializer):
    input_aliases = {
        "refresh": "refresh_token",
        "Refresh": "refresh_token",
        "refresh-token": "refresh_token",
        "refreshToken": "refresh_token",
    }
    refresh_token = serializers.CharField()


class ChangePasswordSerializer(AliasInputMixin, serializers.Serializer):
    input_aliases = {"OTP": "otp", "Password": "password"}
    otp = serializers.RegexField(regex=r"^\d{6}$")
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value
