import { AuthLayout } from "@/components/auth/AuthLayout";
import { AuthForm } from "@/components/auth/AuthForm";

export default function Login() {
  return (
    <AuthLayout>
      <AuthForm mode="login" />
    </AuthLayout>
  );
}
