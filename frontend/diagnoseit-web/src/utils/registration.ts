import { useEffect, useState } from 'react';
import { apiService } from '../services/api';

/** Whether the server accepts new accounts; null until known. If the check fails, sign-up stays on offer. */
export function useRegistrationOpen(): boolean | null {
  const [open, setOpen] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    apiService
      .getRegistrationStatus()
      .then(status => { if (active) setOpen(status.open); })
      .catch(() => { if (active) setOpen(true); });
    return () => { active = false; };
  }, []);
  return open;
}
