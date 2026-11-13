CREATE TABLE "workspaceInvite" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "invitedById" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "workspaceInvite_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "workspaceInvite_email_key" ON "workspaceInvite"("email");
