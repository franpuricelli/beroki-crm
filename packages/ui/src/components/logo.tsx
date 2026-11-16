import { type SVGProps, useId } from "react";

const BODY =
	"M503.42 253.86H648.93V341.65C648.93 343.86 647.15 345.64 644.95 345.64H507.41C505.21 345.64 503.42 343.86 503.42 341.65Z";

export default function Logo(props: SVGProps<SVGSVGElement>) {
	const id = `beroki${useId().replace(/[^\w-]/g, "")}`;
	const shade = `${id}-shade`;
	const tip = `${id}-tip`;
	const clip = `${id}-clip`;

	return (
		<svg
			xmlns="http://www.w3.org/2000/svg"
			width={512}
			height={512}
			viewBox="494.18 182.2 164 164"
			fill="none"
			role="img"
			aria-label="Beroki"
			{...props}
		>
			<defs>
				<linearGradient
					id={shade}
					gradientUnits="userSpaceOnUse"
					x1="-0.03"
					y1="0"
					x2="0.97"
					y2="0"
					gradientTransform="matrix(75.87 -88.71 -88.71 -75.87 621.98 379.91)"
				>
					<stop offset="0" stopColor="#ff4c00" />
					<stop offset="1" stopColor="#c83900" />
				</linearGradient>
				<linearGradient
					id={tip}
					gradientUnits="userSpaceOnUse"
					x1="-0.21"
					y1="0"
					x2="1.22"
					y2="0"
					gradientTransform="matrix(-32.75 -28.71 -28.71 32.75 615.47 184.72)"
				>
					<stop offset="0.18" stopColor="#090807" />
					<stop offset="0.84" stopColor="#a59288" />
				</linearGradient>
				<clipPath id={clip}>
					<path d={BODY} />
				</clipPath>
			</defs>
			<path
				d="M573.36 183.92 503.42 253.85 648.93 253.86 578.99 183.92C577.44 182.36 574.91 182.36 573.36 183.92Z"
				fill="#ffbd95"
			/>
			<path
				d="M573.36 183.92 547.16 210.12H605.2L579 183.92C577.44 182.36 574.92 182.36 573.36 183.92Z"
				fill={`url(#${tip})`}
			/>
			<g clipPath={`url(#${clip})`}>
				<rect
					x="503.42"
					y="253.86"
					width="72.77"
					height="91.78"
					fill="#ff4c00"
				/>
				<rect
					x="576.19"
					y="253.86"
					width="72.74"
					height="91.78"
					fill={`url(#${shade})`}
				/>
			</g>
		</svg>
	);
}
