import { Logo } from "@/components/logo";
import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="flex justify-center">
            <Logo className="h-10 w-auto" />
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Early signals of nonprofit leadership transitions
          </p>
        </div>
        <div className="flex justify-center"><SignIn /></div>
      </div>
    </main>
  )
}