import { APP_LOGO_PATH } from '../utils/branding';
import type { CSSProperties } from 'react';

type AppLogoProps = {
    size?: number;
    className?: string;
    style?: CSSProperties;
};

const AppLogo = ({ size = 44, className, style }: AppLogoProps) => (
    <img
        src={APP_LOGO_PATH}
        alt="TimeWise AI logo"
        className={className}
        style={{
            width: size,
            height: size,
            objectFit: 'contain',
            display: 'block',
            ...style,
        }}
    />
);

export default AppLogo;
