import { Logo } from "@/components/logo";
import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="flex justify-center">
            <Logo className="h-10 w-auto" />
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your account to start finding nonprofit buying signals
          </p>
        </div>
        <SignUp />
      </div>
    </main>
  )
}