import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="font-serif text-3xl text-navy">DEJ Intelligence</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your account to access nonprofit intelligence
          </p>
        </div>
        <SignUp />
      </div>
    </main>
  )
}