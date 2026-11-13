"use client";

import Close from "@carbon/icons-react/es/Close";
import { Button } from "@crm/ui/components/button";
import { Icon } from "@crm/ui/components/icon";
import { SimpleTable, SimpleTableRow } from "@crm/ui/components/simple-table";
import { TableCell } from "@crm/ui/components/table";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@crm/ui/components/tooltip";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { LocalRelativeTime } from "@/components/local-date-time";
import { useCrmCache } from "@/lib/trpc/cache";
import { useTRPC } from "@/lib/trpc/client";

const COLUMNS = [
	{ id: "email", header: "Invited, not signed in yet", width: "w-[70%]" },
	{ id: "invitedAt", header: "Invited", width: "w-[24%]" },
	{ id: "remove", srLabel: "Remove", width: "w-10" },
];

export function PendingInvites() {
	const trpc = useTRPC();
	const cache = useCrmCache();

	const workspace = useQuery(trpc.workspace.get.queryOptions());
	const invites = useQuery(trpc.workspace.invites.queryOptions());

	const revoke = useMutation(
		trpc.workspace.revokeInvite.mutationOptions({
			onSuccess: async () => {
				await cache.workspace();
				toast.success("Invite removed.");
			},
			onError: (error) => toast.error(error.message),
		}),
	);

	const rows = invites.data ?? [];
	if (rows.length === 0) return null;

	const canInvite = workspace.data?.canInvite ?? false;

	return (
		<SimpleTable columns={COLUMNS}>
			{rows.map((invite) => (
				<SimpleTableRow key={invite.id}>
					<TableCell className="truncate py-2.5 pr-3 pl-5">
						{invite.email}
					</TableCell>
					<TableCell className="truncate px-3 py-2.5 text-muted-foreground">
						<LocalRelativeTime date={invite.createdAt} />
					</TableCell>
					<TableCell className="px-3 py-2.5">
						{canInvite ? (
							<Tooltip>
								<TooltipTrigger asChild>
									<Button
										variant="ghost"
										size="icon-xs"
										disabled={revoke.isPending}
										onClick={() => revoke.mutate({ inviteId: invite.id })}
									>
										<Icon icon={Close} />
										<span className="sr-only">
											Remove the invite for {invite.email}
										</span>
									</Button>
								</TooltipTrigger>
								<TooltipContent>Remove invite</TooltipContent>
							</Tooltip>
						) : null}
					</TableCell>
				</SimpleTableRow>
			))}
		</SimpleTable>
	);
}
