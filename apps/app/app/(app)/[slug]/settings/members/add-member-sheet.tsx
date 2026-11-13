"use client";

import Add from "@carbon/icons-react/es/Add";
import { Button } from "@crm/ui/components/button";
import {
	Field,
	FieldDescription,
	FieldGroup,
	FieldLabel,
} from "@crm/ui/components/field";
import { Icon } from "@crm/ui/components/icon";
import { Input } from "@crm/ui/components/input";
import {
	Sheet,
	SheetClose,
	SheetContent,
	SheetDescription,
	SheetFooter,
	SheetHeader,
	SheetTitle,
	SheetTrigger,
} from "@crm/ui/components/sheet";
import { Spinner } from "@crm/ui/components/spinner";
import { useMutation, useQuery } from "@tanstack/react-query";
import { parseAsBoolean, useQueryState } from "nuqs";
import { type ComponentProps, Suspense, useId, useState } from "react";
import { toast } from "sonner";
import { SEARCH_PARAM } from "@/lib/search-param-keys";
import { useCrmCache } from "@/lib/trpc/cache";
import { useTRPC } from "@/lib/trpc/client";

const FORM = "add-member";

function AddMemberButton(props: ComponentProps<typeof Button>) {
	return (
		<Button {...props}>
			<Icon icon={Add} data-icon="inline-start" />
			Add member
		</Button>
	);
}

export function AddMemberSheet() {
	return (
		<Suspense fallback={<AddMemberButton disabled />}>
			<AddMemberForm />
		</Suspense>
	);
}

function AddMemberForm() {
	const trpc = useTRPC();
	const cache = useCrmCache();

	const emailId = useId();

	const [open, setOpen] = useQueryState(
		SEARCH_PARAM.dialog.create,
		parseAsBoolean.withDefault(false),
	);
	const [email, setEmail] = useState("");

	const workspace = useQuery(trpc.workspace.get.queryOptions());
	const allowed = workspace.data?.canInvite ?? false;

	const invite = useMutation(
		trpc.workspace.invite.mutationOptions({
			onSuccess: async (invited) => {
				await cache.invites();
				await setOpen(null);
				setEmail("");
				toast.success(
					`${invited.email} can sign in now. Send them ${window.location.origin}.`,
				);
			},
			onError: (error) => toast.error(error.message),
		}),
	);

	return (
		<Sheet open={open} onOpenChange={(next) => setOpen(next || null)}>
			<SheetTrigger asChild>
				<AddMemberButton disabled={!allowed} />
			</SheetTrigger>

			<SheetContent side="right">
				<SheetHeader>
					<SheetTitle>Add member</SheetTitle>
					<SheetDescription>
						They join the workspace the first time they sign in with this
						address.
					</SheetDescription>
				</SheetHeader>

				<form
					id={FORM}
					className="flex-1 overflow-y-auto px-4"
					onSubmit={(event) => {
						event.preventDefault();
						invite.mutate({ email });
					}}
				>
					<FieldGroup>
						<Field>
							<FieldLabel htmlFor={emailId}>Email</FieldLabel>
							<Input
								id={emailId}
								type="email"
								value={email}
								onChange={(event) => setEmail(event.target.value)}
								placeholder="name@company.com"
								autoComplete="off"
								autoCapitalize="off"
								autoCorrect="off"
								spellCheck={false}
								required
							/>
							<FieldDescription>
								Use the address they sign in with, on Google or Microsoft.
							</FieldDescription>
						</Field>
					</FieldGroup>
				</form>

				<SheetFooter>
					<Button
						type="submit"
						form={FORM}
						disabled={!email.trim() || invite.isPending}
					>
						{invite.isPending ? <Spinner /> : null}
						Add member
					</Button>
					<SheetClose asChild>
						<Button variant="outline">Cancel</Button>
					</SheetClose>
				</SheetFooter>
			</SheetContent>
		</Sheet>
	);
}
