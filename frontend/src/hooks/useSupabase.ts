import { useQuery } from '@tanstack/react-query';
import { supabase } from '../lib/supabase';
import type { Bridge, Contractor, Schaden, Pruefung, Empfehlung } from '../types';

export function useBridges() {
  return useQuery({
    queryKey: ['bridges'],
    queryFn: async () => {
      const { data, error } = await supabase.from('bridges').select('*');
      if (error) {
        console.error('[Supabase] bridges error:', error.code, error.message, error.details);
        throw new Error(`${error.code}: ${error.message}`);
      }
      console.log('[Supabase] bridges loaded:', data?.length, 'rows');
      return (data ?? []) as Bridge[];
    },
  });
}

export function useContractors() {
  return useQuery({
    queryKey: ['contractors'],
    queryFn: async () => {
      const { data, error } = await supabase.from('contractors').select('*');
      if (error) {
        console.error('[Supabase] contractors error:', error.code, error.message);
        throw new Error(`${error.code}: ${error.message}`);
      }
      return (data ?? []) as Contractor[];
    },
  });
}

export function useBridgeDetails(bridgeId: string | null) {
  return useQuery({
    queryKey: ['bridge', bridgeId],
    queryFn: async () => {
      if (!bridgeId) return null;
      
      const [schaeden, pruefungen, empfehlungen] = await Promise.all([
        supabase.from('schaeden').select('*').eq('bridge_id', bridgeId).order('s', { ascending: false }),
        supabase.from('pruefungen').select('*').eq('bridge_id', bridgeId).order('datum', { ascending: false }),
        supabase.from('empfehlungen').select('*').eq('bridge_id', bridgeId).order('nr', { ascending: true })
      ]);

      return {
        schaeden: schaeden.data as Schaden[],
        pruefungen: pruefungen.data as Pruefung[],
        empfehlungen: (empfehlungen.data ?? []) as Empfehlung[],
      };
    },
    enabled: !!bridgeId,
  });
}
