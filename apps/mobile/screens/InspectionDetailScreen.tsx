import React from 'react';
import ResultScreen from './ResultScreen';
import { MainScreenProps } from '../navigation/types';

/**
 * InspectionDetailScreen — Thin wrapper around ResultScreen that lives in
 * a separate route so back-stack semantics differ from a freshly created
 * inspection. The id is forwarded; ResultScreen handles fetching/polling.
 */
type Props = MainScreenProps<'InspectionDetail'>;

export default function InspectionDetailScreen({ navigation, route }: Props) {
  // Re-use ResultScreen by passing through props; both share the
  // `inspectionId` route param shape.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return <ResultScreen navigation={navigation as any} route={{ ...route, params: { inspectionId: route.params.inspectionId } } as any} />;
}
